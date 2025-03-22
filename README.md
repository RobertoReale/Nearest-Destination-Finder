# Nearest Destination Finder

A Python application that helps users find the nearest destination from multiple options using Google Maps Routes API. The app calculates travel times and distances between a starting point and multiple destinations using various transportation modes (public transit, walking, driving, or cycling).

## Features

- Calculate and compare travel times between a starting point and multiple destinations
- Support for different transportation modes:
  - Public Transit
  - Walking
  - Driving
  - Cycling
- Sort destinations by travel time from nearest to farthest
- User-friendly GUI with scrollable destination list
- Detailed results showing travel time and distance for each destination

## Requirements

- Python 3.6 or higher
- Required Python packages:
  - tkinter (included in standard Python installation)
  - requests

## Installation

1. Clone this repository:
```bash
git clone https://github.com/yourusername/nearest-destination-finder.git
cd nearest-destination-finder
```

2. Install the required packages:
```bash
pip install requests
```

3. Run the application:
```bash
python nearest_destination_finder.py
```

## Getting a Google Maps API Key

To use this application, you'll need a Google Maps API key with the following APIs enabled:
- Directions API
- Geocoding API
- Routes API

Follow these steps to obtain an API key:

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable the required APIs:
   - Directions API
   - Geocoding API
   - Routes API
4. Create credentials for an API key
5. (Optional) Restrict the API key to the necessary APIs for security

**Note:** Google Maps Platform requires billing information, but offers a monthly $200 credit, which is typically sufficient for personal use.

## Usage

1. Enter your Google Maps API key in the designated field
2. Input your starting address
3. Add one or more destinations you want to compare
4. Select your preferred transportation mode
5. Click "Find Routes" to calculate and compare travel times
6. View the results ordered from nearest to farthest destination

## Application Structure

- `nearest_destination_finder.py`: Main application file containing the GUI and API integration
- The application uses the following Google Maps APIs:
  - Geocoding API: Convert addresses to geographic coordinates
  - Routes API: Calculate routes, travel times, and distances

## Key Functions

- `geocode_address()`: Converts text addresses to geographic coordinates
- `get_route()`: Retrieves route information between two points
- `find_routes()`: Main function that handles the routing logic and displays results

## Common Issues

- **API Key Errors**: Make sure your API key is valid and has all required APIs enabled
- **Address Not Found**: Check the spelling of addresses or try to be more specific
- **No Route Found**: Some destinations may not be reachable via certain transportation modes

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Google Maps Platform for providing the APIs
- [Tkinter](https://docs.python.org/3/library/tkinter.html) for the GUI framework
