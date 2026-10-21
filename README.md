# SmartRoute

A Python project that visualizes shortest driving routes between two real-world locations using OpenStreetMap data.

## Features

- Load city road networks from OpenStreetMap
- Compute shortest paths using Dijkstra's algorithm
- Interactive route visualization with Folium maps
- Automatic map generation and browser opening

## Requirements

- Python 3.7 or higher
- Internet connection (for downloading OpenStreetMap data)

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

Run the main script:
```bash
python main.py
```

The script will:
1. Load the road network for Pune, India
2. Compute the shortest path between example coordinates (Pune Railway Station to Pune Airport)
3. Generate an interactive map (`route.html`)
4. Automatically open the map in your default browser

## Customizing Routes

To use your own coordinates, edit the following variables in `main.py`:

```python
START_LAT = 18.5204  # Starting latitude
START_LON = 73.8567  # Starting longitude
END_LAT = 18.5822    # Ending latitude
END_LON = 73.9197    # Ending longitude
```

You can also change the city by modifying:
```python
CITY_NAME = "Pune, India"
```

## Output

- **route.html**: Interactive map file with the visualized route
- Console output: Total route length in meters and kilometers

## Libraries Used

- **osmnx**: Fetch and handle OpenStreetMap data
- **networkx**: Compute shortest paths with Dijkstra's algorithm
- **folium**: Create interactive map visualizations

## Example

The default example shows a route from Pune Railway Station to Pune Airport, demonstrating the shortest driving path through Pune's road network.

