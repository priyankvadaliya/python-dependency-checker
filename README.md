# Python Package Dependency Checker

A web application that analyzes Python package dependencies, detects conflicts, and suggests fixes. This tool helps developers identify and resolve package compatibility issues in their `requirements.txt` files.

## Features

- **Dependency Analysis**: Detects conflicts between package versions in your requirements
- **Parallel Processing**: Efficiently analyzes multiple packages concurrently
- **Conflict Detection**: Identifies various types of conflicts (version mismatches, duplicate packages, etc.)
- **Automatic Fix Suggestions**: Recommends solutions to resolve detected conflicts
- **Dependency Visualization**: Generates a visual graph of your package dependencies
- **Modern UI**: Clean, intuitive interface with tab-based navigation

## Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/yourusername/dependency-checker.git
   cd dependency-checker
   ```

2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the application:
   ```bash
   python app.py
   ```

4. Open your browser and go to: http://127.0.0.1:5000

## Usage

1. Enter your package requirements (one per line) in the text area
2. Click "Check Dependencies"
3. Review the detected conflicts in the "Conflicts" tab
4. Apply the suggested fixes using the "Suggested Fixes" tab
5. Explore the dependency graph in the "Dependency Graph" tab

## Example Requirements

You can test the application with the following conflicting requirements:

```
Flask==2.2.3
Werkzeug==1.0.1  # This will conflict with Flask 2.2.3
requests==2.28.2
urllib3==2.0.3  # This will conflict with requests
pandas==1.5.3
numpy==1.20.3  # This will conflict with pandas
```

## Project Structure

The application is organized as follows:

```
dependency-checker/
├── app.py                  # Main application file
├── requirements.txt        # Project dependencies
├── static/                 # Static assets
│   ├── css/
│   │   └── style.css       # CSS styles
│   └── js/
│       └── main.js         # JavaScript functionality
├── templates/              # Flask templates
│   └── index.html          # Main HTML template
├── utils/                  # Utility modules
│   ├── __init__.py         # Make utils a package
│   ├── analyzer.py         # Dependency analysis logic
│   └── visualizer.py       # Graph visualization functions
└── README.md               # Project documentation
```

## Technologies Used

- **Backend**: Python, Flask
- **Dependency Analysis**: PyPI API, concurrent processing
- **Visualization**: NetworkX, Matplotlib
- **Frontend**: HTML, CSS, JavaScript
- **UI Components**: Font Awesome, Inter font

## License

MIT

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.