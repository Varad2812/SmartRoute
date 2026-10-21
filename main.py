#!/usr/bin/env python3
import osmnx as ox
import networkx as nx
import folium
from folium import plugins
import streamlit as st
import pandas as pd
import os

st.set_page_config(
    page_title="SmartRoute - Interactive Route Planner",
    page_icon="🗺️",
    layout="wide"
)

@st.cache_data
def load_city_graph(city_name="Pune, India"):
    with st.spinner(f"Loading road network for {city_name}..."):
        graph = ox.graph_from_place(city_name, network_type='drive')
    return graph


def find_nearest_node(graph, latitude, longitude):
    try:
        node_id = ox.nearest_nodes(graph, [longitude], [latitude])[0]
        return node_id
    except Exception as e:
        st.error(f"Error finding nearest node: {str(e)}")
        return None


def compute_path_metrics(graph, path):
    if len(path) < 2:
        return {}
    
    total_length = 0
    num_turns = 0
    narrow_roads = 0
    one_way_segments = 0
    max_speed_segments = []
    road_types = {}
    
    for i in range(len(path) - 1):
        u, v = path[i], path[i+1]
        
        edge_data = graph[u][v][0]
        
        length = edge_data.get('length', 0)
        total_length += length
        
        if i > 0:
            prev_node = path[i-1]
            curr_node = path[i]
            next_node = path[i+1]
            
            try:
                prev_coords = (graph.nodes[prev_node]['y'], graph.nodes[prev_node]['x'])
                curr_coords = (graph.nodes[curr_node]['y'], graph.nodes[curr_node]['x'])
                next_coords = (graph.nodes[next_node]['y'], graph.nodes[next_node]['x'])
                
                import math
                def angle_between_points(p1, p2, p3):
                    v1 = (p2[0] - p1[0], p2[1] - p1[1])
                    v2 = (p3[0] - p2[0], p3[1] - p2[1])
                    dot = v1[0]*v2[0] + v1[1]*v2[1]
                    det = v1[0]*v2[1] - v1[1]*v2[0]
                    angle = math.atan2(det, dot)
                    return abs(math.degrees(angle))
                
                angle = angle_between_points(prev_coords, curr_coords, next_coords)
                if angle > 30:
                    num_turns += 1
            except:
                pass
        
        highway = edge_data.get('highway', 'unknown')
        if isinstance(highway, list):
            highway = highway[0] if highway else 'unknown'
        
        road_types[highway] = road_types.get(highway, 0) + length
        
        if highway in ['residential', 'service', 'track', 'path']:
            narrow_roads += length
        
        if edge_data.get('oneway') == 'yes':
            one_way_segments += length
        
        maxspeed = edge_data.get('maxspeed', None)
        if maxspeed:
            try:
                if isinstance(maxspeed, list):
                    maxspeed = maxspeed[0]
                if isinstance(maxspeed, str):
                    maxspeed = int(maxspeed.replace(' mph', '').replace(' km/h', ''))
                max_speed_segments.append(maxspeed)
            except:
                pass
    
    avg_speed = sum(max_speed_segments) / len(max_speed_segments) if max_speed_segments else None
    
    return {
        'total_length': total_length,
        'num_turns': num_turns,
        'narrow_roads_km': narrow_roads / 1000,
        'one_way_km': one_way_segments / 1000,
        'avg_speed_limit': avg_speed,
        'road_types': road_types,
        'num_segments': len(path) - 1
    }


def find_k_shortest_paths(graph, start_node, end_node, k=3, weight='length'):
    try:
        paths = []
        
        try:
            shortest = nx.shortest_path(graph, start_node, end_node, weight=weight)
            paths.append(shortest)
        except nx.NetworkXNoPath:
            return []
        
        if k == 1:
            return paths
        
        edges_to_remove = []
        for i in range(len(shortest) - 1):
            u, v = shortest[i], shortest[i+1]
            if graph.has_edge(u, v):
                edges_to_remove.append((u, v))
        
        max_attempts = min(k * 3, len(edges_to_remove) * 2)
        
        for attempt in range(max_attempts):
            if len(paths) >= k:
                break
                
            G_temp = graph.copy()
            
            if attempt < len(edges_to_remove):
                u, v = edges_to_remove[attempt]
                if G_temp.has_edge(u, v):
                    G_temp.remove_edge(u, v)
            else:
                num_edges = min(2, len(edges_to_remove))
                for j in range(num_edges):
                    idx = (attempt + j) % len(edges_to_remove)
                    u, v = edges_to_remove[idx]
                    if G_temp.has_edge(u, v):
                        G_temp.remove_edge(u, v)
            try:
                alt_path = nx.shortest_path(G_temp, start_node, end_node, weight=weight)
                
                is_duplicate = False
                for existing_path in paths:
                    if len(alt_path) == len(existing_path) and alt_path == existing_path:
                        is_duplicate = True
                        break
                    if abs(len(alt_path) - len(existing_path)) / max(len(alt_path), len(existing_path)) < 0.1:
                        overlap = len(set(alt_path) & set(existing_path)) / max(len(alt_path), len(existing_path))
                        if overlap > 0.9:
                            is_duplicate = True
                            break
                
                if not is_duplicate:
                    paths.append(alt_path)
                    if len(paths) >= k:
                        break
            except nx.NetworkXNoPath:
                continue
        
        if len(paths) < k:
            for attempt in range(min(k - len(paths), len(shortest) - 2)):
                if len(paths) >= k:
                    break
                    
                G_temp = graph.copy()
                if attempt + 1 < len(shortest) - 1:
                    node_to_remove = shortest[attempt + 1]
                    G_temp.remove_node(node_to_remove)
                    
                    try:
                        alt_path = nx.shortest_path(G_temp, start_node, end_node, weight=weight)
                        
                        is_duplicate = False
                        for existing_path in paths:
                            if alt_path == existing_path:
                                is_duplicate = True
                                break
                        
                        if not is_duplicate:
                            paths.append(alt_path)
                    except (nx.NetworkXNoPath, nx.NetworkXError):
                        continue
        
        return paths[:k]
    except Exception as e:
        st.error(f"Error finding alternate paths: {str(e)}")
        return []


def create_route_map(graph, paths, start_lat, start_lon, end_lat, end_lon, path_metrics_list):
    center_lat = (start_lat + end_lat) / 2
    center_lon = (start_lon + end_lon) / 2
    
    route_map = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=13,
        tiles='OpenStreetMap'
    )
    
    if path_metrics_list:
        distances = [m.get('total_length', float('inf')) for m in path_metrics_list]
        fastest_idx = distances.index(min(distances))
    else:
        fastest_idx = 0
    
    colors = ['#0066FF', '#FF6600', '#00CC66', '#CC00CC', '#FFCC00']
    color_names = ['Blue (Fastest)', 'Orange', 'Green', 'Purple', 'Yellow']
    
    fastest_path = paths[fastest_idx] if fastest_idx < len(paths) else None
    other_paths = [(idx, path) for idx, path in enumerate(paths) if idx != fastest_idx]
    
    for idx, path in other_paths:
        if not path:
            continue
            
        route_coords = [(graph.nodes[node]['y'], graph.nodes[node]['x']) for node in path]
        
        color_idx = (idx - 1) % (len(colors) - 1) + 1
        color = colors[color_idx]
        route_label = f"Route {idx + 1}"
        
        metrics = path_metrics_list[idx] if idx < len(path_metrics_list) else {}
        length_km = metrics.get('total_length', 0) / 1000
        
        popup_text = f"<b>{route_label}</b><br>"
        popup_text += f"<b>Color: {color}</b><br>"
        popup_text += f"Distance: {length_km:.2f} km<br>"
        popup_text += f"Turns: {metrics.get('num_turns', 0)}<br>"
        if metrics.get('narrow_roads_km', 0) > 0:
            popup_text += f"Narrow roads: {metrics.get('narrow_roads_km', 0):.2f} km"
        
        folium.PolyLine(
            route_coords,
            color=color,
            weight=6,
            opacity=0.7,
            dashArray='10, 5',
            popup=folium.Popup(popup_text, max_width=250)
        ).add_to(route_map)
    
    if fastest_path:
        route_coords = [(graph.nodes[node]['y'], graph.nodes[node]['x']) for node in fastest_path]
        color = '#0066FF'
        route_label = f"Route {fastest_idx + 1} (Fastest)"
        
        metrics = path_metrics_list[fastest_idx] if fastest_idx < len(path_metrics_list) else {}
        length_km = metrics.get('total_length', 0) / 1000
        
        popup_text = f"<b>{route_label}</b><br>"
        popup_text += f"<b>Color: {color}</b><br>"
        popup_text += f"Distance: {length_km:.2f} km<br>"
        popup_text += f"Turns: {metrics.get('num_turns', 0)}<br>"
        if metrics.get('narrow_roads_km', 0) > 0:
            popup_text += f"Narrow roads: {metrics.get('narrow_roads_km', 0):.2f} km"
        
        folium.PolyLine(
            route_coords,
            color=color,
            weight=8,
            opacity=0.9,
            popup=folium.Popup(popup_text, max_width=250)
        ).add_to(route_map)
    
    folium.Marker(
        [start_lat, start_lon],
        popup='Start',
        icon=folium.Icon(color='green', icon='play', prefix='fa')
    ).add_to(route_map)
    
    folium.Marker(
        [end_lat, end_lon],
        popup='End',
        icon=folium.Icon(color='red', icon='stop', prefix='fa')
    ).add_to(route_map)
    
    return route_map


def analyze_path_flaws(metrics):
    flaws = []
    
    narrow_km = metrics.get('narrow_roads_km', 0)
    total_km = metrics.get('total_length', 0) / 1000
    if narrow_km > 0:
        percentage = (narrow_km / total_km * 100) if total_km > 0 else 0
        if percentage > 30:
            flaws.append(f"⚠️ High percentage of narrow roads ({percentage:.1f}%)")
        elif percentage > 10:
            flaws.append(f"⚠️ Some narrow roads ({percentage:.1f}%)")
    
    num_turns = metrics.get('num_turns', 0)
    if num_turns > 20:
        flaws.append(f"⚠️ Many turns ({num_turns}) - may be complex to navigate")
    elif num_turns > 10:
        flaws.append(f"⚠️ Moderate number of turns ({num_turns})")
    
    one_way_km = metrics.get('one_way_km', 0)
    if one_way_km > total_km * 0.5:
        flaws.append(f"⚠️ Significant portion on one-way roads ({one_way_km:.2f} km)")
    
    avg_speed = metrics.get('avg_speed_limit')
    if avg_speed and avg_speed < 40:
        flaws.append(f"⚠️ Low average speed limit ({avg_speed} km/h)")
    
    num_segments = metrics.get('num_segments', 0)
    if num_segments > 100:
        flaws.append(f"⚠️ Complex route with many segments ({num_segments})")
    
    if not flaws:
        flaws.append("✅ No significant issues detected")
    
    return flaws


def main():
    st.title("🗺️ SmartRoute - Interactive Route Planner")
    st.markdown("Find the best route with alternate paths and detailed analysis")
    
    with st.sidebar:
        st.header("📍 Route Input")
        
        city_name = st.text_input("City", value="Pune, India", help="Enter city name for map loading")
        
        col1, col2 = st.columns(2)
        with col1:
            source_lat = st.number_input("Source Latitude", value=18.5204, format="%.6f")
            source_lon = st.number_input("Source Longitude", value=73.8567, format="%.6f")
        with col2:
            dest_lat = st.number_input("Destination Latitude", value=18.5822, format="%.6f")
            dest_lon = st.number_input("Destination Longitude", value=73.9197, format="%.6f")
        
        num_routes = st.slider("Number of Routes", 1, 5, 3, help="Number of alternate routes to find")
        
        find_routes = st.button("🔍 Find Routes", type="primary", use_container_width=True)
    
    if find_routes:
        if not all([source_lat, source_lon, dest_lat, dest_lon]):
            st.error("❌ Please provide valid source and destination coordinates")
            st.stop()
        graph = load_city_graph(city_name)
        st.success(f"Loaded graph with {len(graph.nodes):,} nodes and {len(graph.edges):,} edges")
        
        # Find nearest nodes
        start_node = find_nearest_node(graph, source_lat, source_lon)
        end_node = find_nearest_node(graph, dest_lat, dest_lon)
        
        if not start_node or not end_node:
            st.error("Could not find valid nodes on the road network")
            st.stop()
        
        # Find paths
        with st.spinner("Finding routes..."):
            paths = find_k_shortest_paths(graph, start_node, end_node, k=num_routes)
        
        if not paths:
            st.error("No routes found between the selected points")
            st.stop()
        
        # Compute metrics for each path
        path_metrics_list = []
        for path in paths:
            metrics = compute_path_metrics(graph, path)
            path_metrics_list.append(metrics)
        
        # Find fastest route
        if path_metrics_list:
            distances = [m.get('total_length', float('inf')) for m in path_metrics_list]
            fastest_idx = distances.index(min(distances))
        else:
            fastest_idx = 0
        
        # Display routes comparison
        st.header("📊 Route Comparison")
        
        # Color mapping
        colors = ['#0066FF', '#FF6600', '#00CC66', '#CC00CC', '#FFCC00']
        color_names = ['Blue (Fastest)', 'Orange', 'Green', 'Purple', 'Yellow']
        
        # Create comparison table
        comparison_data = []
        for idx, (path, metrics) in enumerate(zip(paths, path_metrics_list)):
            if idx == fastest_idx:
                route_name = f"Route {idx + 1} (Fastest)"
                color_name = "Blue"
            else:
                route_name = f"Route {idx + 1}"
                color_idx = (idx - 1) % (len(colors) - 1) + 1
                color_name = color_names[color_idx]
            
            comparison_data.append({
                'Route': route_name,
                'Color': color_name,
                'Distance (km)': f"{metrics.get('total_length', 0) / 1000:.2f}",
                'Turns': metrics.get('num_turns', 0),
                'Narrow Roads (km)': f"{metrics.get('narrow_roads_km', 0):.2f}",
                'One-way (km)': f"{metrics.get('one_way_km', 0):.2f}",
                'Segments': metrics.get('num_segments', 0)
            })
        
        df = pd.DataFrame(comparison_data)
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        # Display color legend
        st.markdown("### 🎨 Route Colors:")
        st.caption("💡 Fastest route is shown as a solid blue line. Alternate routes are shown as dashed lines to make overlaps visible.")
        legend_cols = st.columns(len(paths))
        for idx, (path, metrics) in enumerate(zip(paths, path_metrics_list)):
            with legend_cols[idx]:
                if idx == fastest_idx:
                    color = '#0066FF'
                    label = f"Route {idx + 1} (Fastest) - Solid"
                else:
                    color_idx = (idx - 1) % (len(colors) - 1) + 1
                    color = colors[color_idx]
                    label = f"Route {idx + 1} - Dashed"
                
                st.markdown(f'<div style="background-color: {color}; color: white; padding: 10px; border-radius: 5px; text-align: center; font-weight: bold;">{label}</div>', unsafe_allow_html=True)
        
        # Display route details and flaws
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("🗺️ Interactive Map")
            route_map = create_route_map(graph, paths, source_lat, source_lon, dest_lat, dest_lon, path_metrics_list)
            st.components.v1.html(route_map._repr_html_(), height=600)
        
        with col2:
            st.subheader("📋 Route Details & Analysis")
            
            for idx, (path, metrics) in enumerate(zip(paths, path_metrics_list)):
                # Determine route color and label
                if idx == fastest_idx:
                    route_label = f"Route {idx + 1} (Fastest) - {metrics.get('total_length', 0) / 1000:.2f} km"
                    route_color = "Blue (#0066FF)"
                else:
                    color_idx = (idx - 1) % (len(colors) - 1) + 1
                    route_label = f"Route {idx + 1} - {metrics.get('total_length', 0) / 1000:.2f} km"
                    route_color = f"{color_names[color_idx]} ({colors[color_idx]})"
                
                with st.expander(route_label, expanded=(idx == 0)):
                    st.markdown(f"**🎨 Color:** {route_color}")
                    st.write(f"**Distance:** {metrics.get('total_length', 0) / 1000:.2f} km")
                    st.write(f"**Number of turns:** {metrics.get('num_turns', 0)}")
                    st.write(f"**Route segments:** {metrics.get('num_segments', 0)}")
                    
                    if metrics.get('narrow_roads_km', 0) > 0:
                        st.write(f"**Narrow roads:** {metrics.get('narrow_roads_km', 0):.2f} km")
                    
                    if metrics.get('one_way_km', 0) > 0:
                        st.write(f"**One-way roads:** {metrics.get('one_way_km', 0):.2f} km")
                    
                    if metrics.get('avg_speed_limit'):
                        st.write(f"**Avg speed limit:** {metrics.get('avg_speed_limit')} km/h")
                    
                    # Show flaws
                    st.markdown("**Potential Issues:**")
                    flaws = analyze_path_flaws(metrics)
                    for flaw in flaws:
                        st.markdown(flaw)
                    
                    # Road types breakdown
                    if metrics.get('road_types'):
                        st.markdown("**Road Types:**")
                        road_types_str = ", ".join([f"{k}: {v/1000:.2f}km" for k, v in list(metrics['road_types'].items())[:5]])
                        st.caption(road_types_str)
    else:
        st.info("👈 Enter source and destination in the sidebar, then click 'Find Routes'")
        st.markdown("""
        ### Features:
        - 🗺️ **Interactive Map**: Visualize multiple routes on an interactive map
        - 📊 **Route Comparison**: Compare distance, turns, and road conditions
        - ⚠️ **Flaw Detection**: Identify potential issues like narrow roads, many turns, etc.
        - 🔄 **Alternate Paths**: Find multiple route options between two points
        
        ### How to use:
        1. Enter your city name
        2. Enter source and destination coordinates
        3. Select number of routes to find
        4. Click "Find Routes"
        """)


if __name__ == "__main__":
    main()