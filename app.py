import os
import sys
import subprocess
import tempfile
import json
import re
import networkx as nx
import concurrent.futures
import time
import threading
from flask import Flask, render_template, request, jsonify
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import base64
from io import BytesIO
import requests
from functools import lru_cache

app = Flask(__name__)
cache = {}  # Simple in-memory cache

@app.route('/')
def index():
    return render_template('index.html')

def parse_dependencies(requirements_text):
    """Parse requirements text into list of package names and versions."""
    packages = []
    for line in requirements_text.strip().split('\n'):
        # Skip comments and empty lines
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        
        packages.append(line)
    
    return packages

@lru_cache(maxsize=100)
def get_package_metadata(package_name):
    """
    Get package metadata from PyPI.
    This is much faster than using pip commands.
    """
    try:
        response = requests.get(f"https://pypi.org/pypi/{package_name}/json", timeout=5)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception:
        return None

def extract_requirements_from_metadata(metadata):
    """Extract requirements from PyPI metadata."""
    if not metadata or 'info' not in metadata:
        return []
    
    requires_dist = metadata['info'].get('requires_dist', [])
    if not requires_dist:
        return []
    
    requirements = []
    for req in requires_dist:
        # Parse requirement string
        if ";" in req:  # Has environment markers
            req_name = req.split(";")[0].strip()
        else:
            req_name = req
        
        # Extract just the package name
        package_name = req_name.split(" ")[0].strip()
        requirements.append(package_name)
    
    return requirements

def check_package_conflict(req, all_requirements):
    """Check if a single package has conflicts with other requirements."""
    conflicts = []
    suggestions = []
    
    # Extract package name and version
    package_name = req.split('==')[0].split('>=')[0].split('<=')[0].split('>')[0].split('<')[0].split('~=')[0].strip()
    version_spec = None
    if '==' in req:
        version_spec = '=='
        version = req.split('==')[1]
    elif '>=' in req:
        version_spec = '>='
        version = req.split('>=')[1]
    elif '<=' in req:
        version_spec = '<='
        version = req.split('<=')[1]
    elif '>' in req:
        version_spec = '>'
        version = req.split('>')[1]
    elif '<' in req:
        version_spec = '<'
        version = req.split('<')[1]
    elif '~=' in req:
        version_spec = '~='
        version = req.split('~=')[1]
    
    # Check if package exists
    metadata = get_package_metadata(package_name)
    if not metadata:
        conflicts.append({
            'package': package_name,
            'error': f"Package '{package_name}' not found on PyPI",
            'type': 'missing_package',
            'suggestion': f"Check if package name is correct or if it's a private package"
        })
        return conflicts, suggestions
    
    # Check if the specified version exists
    if version_spec == '==' and version:
        if version not in metadata.get('releases', {}):
            conflicts.append({
                'package': package_name,
                'error': f"Version {version} not found for package '{package_name}'",
                'type': 'version_not_found',
                'suggestion': f"Check available versions at https://pypi.org/project/{package_name}/"
            })
            
            # Suggest the latest version
            latest_version = metadata['info'].get('version')
            if latest_version:
                suggestions.append(f"{package_name}=={latest_version}")
            
            return conflicts, suggestions
    
    # Get package dependencies
    dependencies = extract_requirements_from_metadata(metadata)
    
    # Check for conflicts with other requirements
    for other_req in all_requirements:
        if other_req == req:
            continue
        
        other_package = other_req.split('==')[0].split('>=')[0].split('<=')[0].split('>')[0].split('<')[0].split('~=')[0].strip()
        
        # Check for duplicate package with different version
        if other_package == package_name and '==' in other_req and '==' in req:
            this_version = req.split('==')[1]
            other_version = other_req.split('==')[1]
            
            if this_version != other_version:
                conflicts.append({
                    'package': package_name,
                    'error': f"Duplicate package '{package_name}' with different versions: {this_version} and {other_version}",
                    'type': 'duplicate_package',
                    'suggestion': f"Use only one version or use a compatible version specifier like {package_name}~={this_version}"
                })
                
                # Suggest using the newer version
                versions = [this_version, other_version]
                versions.sort(reverse=True)  # Simple version sort, not semantic
                suggestions.append(f"{package_name}=={versions[0]}")
    
    # For each dependency, check if it conflicts with other requirements
    for dep in dependencies:
        dep_name = dep.split(' ')[0]
        
        for other_req in all_requirements:
            other_package = other_req.split('==')[0].split('>=')[0].split('<=')[0].split('>')[0].split('<')[0].split('~=')[0].strip()
            
            if other_package == dep_name:
                # This is a potential conflict, check versions
                # Note: This is a simplified check and could be enhanced with proper version parsing
                if '==' in other_req and ('<' in dep or '>' in dep):
                    other_version = other_req.split('==')[1]
                    
                    # Simple check for version conflicts
                    if ('<' in dep and other_version >= dep.split('<')[1].strip()) or \
                       ('>' in dep and other_version <= dep.split('>')[1].strip()):
                        conflicts.append({
                            'package': package_name,
                            'error': f"{package_name} requires {dep}, but found {other_req}",
                            'type': 'dependency_conflict',
                            'suggestion': f"Adjust {other_package} version to be compatible with {dep}"
                        })
                        
                        # Suggest a compatible version
                        if '<' in dep:
                            version = dep.split('<')[1].strip()
                            major, minor = version.split('.')[:2]
                            suggested_version = f"{major}.{str(int(minor) - 1)}"
                            suggestions.append(f"{other_package}<{version}")
                        elif '>' in dep:
                            version = dep.split('>')[1].strip()
                            major, minor = version.split('.')[:2]
                            suggested_version = f"{major}.{str(int(minor) + 1)}"
                            suggestions.append(f"{other_package}>{version}")
    
    return conflicts, suggestions

def detect_conflicts_parallel(requirements):
    """
    Analyze requirements for conflicts using parallel processing.
    """
    all_conflicts = []
    all_suggestions = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(10, len(requirements))) as executor:
        # Submit all tasks
        future_to_req = {
            executor.submit(check_package_conflict, req, requirements): req 
            for req in requirements
        }
        
        # Process results as they complete
        for future in concurrent.futures.as_completed(future_to_req):
            conflicts, suggestions = future.result()
            all_conflicts.extend(conflicts)
            all_suggestions.extend(suggestions)
    
    return all_conflicts, all_suggestions

def get_limited_dependency_tree(requirements, max_depth=2):
    """Generate a simplified dependency tree for visualization."""
    tree_data = []
    
    for req in requirements:
        package_name = req.split('==')[0].split('>=')[0].split('<=')[0].split('>')[0].split('<')[0].split('~=')[0].strip()
        
        # Get package metadata
        metadata = get_package_metadata(package_name)
        if not metadata:
            continue
        
        # Create package node
        package_info = {
            'package_name': package_name,
            'dependencies': []
        }
        
        # Add first level dependencies only (for performance)
        dependencies = extract_requirements_from_metadata(metadata)
        for dep in dependencies:
            dep_name = dep.split(' ')[0]
            package_info['dependencies'].append({
                'package_name': dep_name,
                'dependencies': []
            })
        
        tree_data.append(package_info)
    
    return tree_data

def create_dependency_graph(dependency_tree):
    """Create a NetworkX graph from dependency tree data."""
    G = nx.DiGraph()
    
    # Add all packages as nodes
    for package_info in dependency_tree:
        package_name = package_info['package_name']
        G.add_node(package_name)
        
        # Add dependencies as edges
        for dependency in package_info.get('dependencies', []):
            dependency_name = dependency['package_name']
            G.add_node(dependency_name)
            G.add_edge(package_name, dependency_name)
    
    return G

def plot_dependency_graph(G):
    """Plot the dependency graph and return it as a base64 encoded image."""
    plt.figure(figsize=(12, 8))
    
    if len(G.nodes()) > 0:
        pos = nx.spring_layout(G, seed=42)  # For reproducibility
        nx.draw(G, pos, with_labels=True, node_color='skyblue', node_size=1500, 
               font_size=10, font_weight='bold', arrows=True, arrowsize=15)
    else:
        plt.text(0.5, 0.5, "No dependencies to visualize", 
                 horizontalalignment='center', verticalalignment='center',
                 fontsize=14)
    
    # Save the plot to a BytesIO object
    buffer = BytesIO()
    plt.savefig(buffer, format='png')
    buffer.seek(0)
    image_data = base64.b64encode(buffer.getvalue()).decode('utf-8')
    plt.close()
    
    return image_data

@app.route('/check_dependencies', methods=['POST'])
def check_dependencies():
    requirements_text = request.form.get('requirements', '')
    
    # Parse requirements text into list of package names
    requirements = parse_dependencies(requirements_text)
    
    if not requirements:
        return jsonify({'error': 'No valid packages found in the requirements.'})
    
    # Start a background timer to track performance
    start_time = time.time()
    
    # Detect conflicts using parallel processing
    conflicts, suggestions = detect_conflicts_parallel(requirements)
    
    # Generate a simplified dependency tree
    dependency_tree = get_limited_dependency_tree(requirements)
    
    # Create and plot dependency graph
    graph_image = None
    if dependency_tree:
        try:
            G = create_dependency_graph(dependency_tree)
            graph_image = plot_dependency_graph(G)
        except Exception as e:
            return jsonify({'graph_error': str(e)})
    
    # Generate fixed requirements
    fixed_requirements = []
    applied_suggestions = {}
    
    if conflicts:
        # Start with original requirements
        req_dict = {
            req.split('==')[0].split('>=')[0].split('<=')[0].split('>')[0].split('<')[0].split('~=')[0].strip(): req
            for req in requirements
        }
        
        # Apply unique suggestions
        for suggestion in suggestions:
            pkg_name = suggestion.split('==')[0].split('>=')[0].split('<=')[0].split('>')[0].split('<')[0].split('~=')[0].strip()
            req_dict[pkg_name] = suggestion
            applied_suggestions[pkg_name] = suggestion
        
        fixed_requirements = list(req_dict.values())
    
    # Calculate performance metrics
    execution_time = time.time() - start_time
    
    # Build response data
    response_data = {
        'requirements': requirements,
        'conflicts': conflicts,
        'dependency_tree': dependency_tree,
        'graph_image': graph_image,
        'fixed_requirements': fixed_requirements if conflicts else [],
        'applied_suggestions': applied_suggestions,
        'execution_time': f"{execution_time:.2f} seconds"
    }
    
    return jsonify(response_data)

if __name__ == '__main__':
    # Create templates directory if it doesn't exist
    os.makedirs('templates', exist_ok=True)
    
    # Create index.html template
    with open('templates/index.html', 'w') as f:
        f.write('''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Python Package Dependency Checker</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
    <style>
        :root {
            --primary-color: #3f51b5;
            --primary-light: #757de8;
            --primary-dark: #002984;
            --secondary-color: #4caf50;
            --secondary-light: #80e27e;
            --secondary-dark: #087f23;
            --danger-color: #f44336;
            --warning-color: #ff9800;
            --info-color: #2196f3;
            --success-color: #4caf50;
            --gray-100: #f7f7f7;
            --gray-200: #eeeeee;
            --gray-300: #e0e0e0;
            --gray-400: #bdbdbd;
            --gray-500: #9e9e9e;
            --gray-600: #757575;
            --gray-700: #616161;
            --gray-800: #424242;
            --gray-900: #212121;
            --border-radius: 8px;
            --box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            --transition: all 0.3s ease;
        }
        
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }
        
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
            line-height: 1.6;
            color: var(--gray-800);
            background-color: #f5f7fa;
            margin: 0;
            padding: 0;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 2rem;
        }
        
        header {
            background: linear-gradient(135deg, var(--primary-color), var(--primary-dark));
            color: white;
            text-align: center;
            padding: 2rem 1rem;
            margin-bottom: 2rem;
            border-radius: var(--border-radius);
            box-shadow: var(--box-shadow);
        }
        
        h1, h2, h3, h4 {
            margin-bottom: 1rem;
            font-weight: 600;
            line-height: 1.3;
        }
        
        h1 {
            font-size: 2.5rem;
            margin-bottom: 0.5rem;
        }
        
        h2 {
            font-size: 1.8rem;
            color: var(--primary-color);
            border-bottom: 2px solid var(--primary-light);
            padding-bottom: 0.5rem;
            margin-top: 2rem;
        }
        
        h3 {
            font-size: 1.4rem;
            color: var(--gray-800);
            margin-top: 1.5rem;
        }
        
        p {
            margin-bottom: 1rem;
        }
        
        .card {
            background-color: white;
            border-radius: var(--border-radius);
            box-shadow: var(--box-shadow);
            overflow: hidden;
            margin-bottom: 2rem;
            transition: var(--transition);
        }
        
        .card:hover {
            box-shadow: 0 10px 15px rgba(0, 0, 0, 0.1);
        }
        
        .card-header {
            background-color: var(--primary-color);
            color: white;
            padding: 1rem;
            font-weight: 600;
        }
        
        .card-body {
            padding: 1.5rem;
        }
        
        textarea {
            width: 100%;
            min-height: 200px;
            padding: 1rem;
            margin-bottom: 1rem;
            border: 1px solid var(--gray-300);
            border-radius: var(--border-radius);
            font-family: 'Courier New', monospace;
            font-size: 0.9rem;
            transition: var(--transition);
            resize: vertical;
        }
        
        textarea:focus {
            outline: none;
            border-color: var(--primary-color);
            box-shadow: 0 0 0 2px rgba(63, 81, 181, 0.2);
        }
        
        button {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 0.75rem 1.5rem;
            border: none;
            border-radius: var(--border-radius);
            font-weight: 600;
            cursor: pointer;
            transition: var(--transition);
            font-size: 1rem;
        }
        
        .btn-primary {
            background-color: var(--primary-color);
            color: white;
        }
        
        .btn-primary:hover {
            background-color: var(--primary-dark);
        }
        
        .btn-success {
            background-color: var(--success-color);
            color: white;
        }
        
        .btn-success:hover {
            background-color: var(--secondary-dark);
        }
        
        .btn-info {
            background-color: var(--info-color);
            color: white;
        }
        
        .btn-info:hover {
            background-color: #0b7dda;
        }
        
        .btn-sm {
            padding: 0.5rem 1rem;
            font-size: 0.875rem;
        }
        
        .btn-icon {
            margin-right: 0.5rem;
        }
        
        .loading {
            display: none;
            text-align: center;
            margin: 2rem 0;
        }
        
        .loader {
            display: inline-block;
            width: 40px;
            height: 40px;
            border: 4px solid rgba(63, 81, 181, 0.2);
            border-radius: 50%;
            border-top: 4px solid var(--primary-color);
            animation: spin 1s linear infinite;
        }
        
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        .result-section {
            display: none;
            animation: fadeIn 0.5s ease;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        .performance-info {
            display: flex;
            align-items: center;
            background-color: var(--gray-100);
            padding: 0.75rem 1rem;
            border-radius: var(--border-radius);
            margin-bottom: 1.5rem;
            font-size: 0.9rem;
            color: var(--gray-700);
        }
        
        .performance-info i {
            margin-right: 0.5rem;
            color: var(--primary-color);
        }
        
        .package-list {
            margin-top: 1rem;
        }
        
        .package {
            background-color: white;
            padding: 1rem;
            margin-bottom: 1rem;
            border-radius: var(--border-radius);
            border-left: 4px solid;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
            transition: var(--transition);
        }
        
        .package:hover {
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
        }
        
        .package-header {
            font-weight: 600;
            margin-bottom: 0.5rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .package-name {
            display: flex;
            align-items: center;
        }
        
        .package-name i {
            margin-right: 0.5rem;
        }
        
        .package-type {
            font-size: 0.75rem;
            padding: 0.25rem 0.5rem;
            border-radius: 20px;
            color: white;
            background-color: var(--gray-500);
        }
        
        .error-message {
            font-family: 'Courier New', monospace;
            font-size: 0.85rem;
            background-color: var(--gray-100);
            padding: 0.75rem;
            border-radius: 4px;
            margin: 0.5rem 0;
            white-space: pre-wrap;
            overflow-x: auto;
        }
        
        .suggestion {
            background-color: #e3f2fd;
            border-left: 4px solid var(--info-color);
            padding: 1rem;
            margin-top: 0.75rem;
            border-radius: 4px;
            position: relative;
        }
        
        .suggestion-header {
            font-weight: 600;
            margin-bottom: 0.5rem;
            display: flex;
            align-items: center;
        }
        
        .suggestion-header i {
            margin-right: 0.5rem;
            color: var(--info-color);
        }
        
        .conflict { border-left-color: var(--danger-color); }
        .direct_conflict, .duplicate_package { border-left-color: #d32f2f; }
        .version_conflict, .dependency_conflict { border-left-color: #c62828; }
        .installation_error, .missing_package, .version_not_found { border-left-color: #d50000; }
        .system_error { border-left-color: #b71c1c; }
        .analysis_error { border-left-color: var(--warning-color); }
        
        .fixed-requirements {
            background-color: #e8f5e9;
            border: 1px dashed var(--success-color);
            border-radius: var(--border-radius);
            padding: 1.5rem;
            margin-top: 1.5rem;
            position: relative;
        }
        
        .fixed-requirements-header {
            position: absolute;
            top: -12px;
            left: 20px;
            background-color: white;
            padding: 0 10px;
            color: var(--success-color);
            font-weight: 600;
            font-size: 0.9rem;
        }
        
        .fixed-requirements-actions {
            display: flex;
            justify-content: flex-end;
            margin-top: 1rem;
        }
        
        .fixed-requirements-actions button {
            margin-left: 0.5rem;
        }
        
        pre {
            background-color: var(--gray-100);
            padding: 1rem;
            border-radius: 4px;
            overflow-x: auto;
            font-family: 'Courier New', monospace;
            font-size: 0.9rem;
            margin: 0.5rem 0;
        }
        
        .graph-container {
            margin-top: 2rem;
            text-align: center;
        }
        
        .graph-container img {
            max-width: 100%;
            border-radius: var(--border-radius);
            box-shadow: var(--box-shadow);
            margin-top: 1rem;
        }
        
        .tab-container {
            margin-top: 2rem;
        }
        
        .tabs {
            display: flex;
            border-bottom: 2px solid var(--gray-300);
            margin-bottom: 1.5rem;
        }
        
        .tab {
            padding: 0.75rem 1.5rem;
            cursor: pointer;
            font-weight: 600;
            color: var(--gray-600);
            border-bottom: 2px solid transparent;
            margin-bottom: -2px;
            transition: var(--transition);
        }
        
        .tab.active {
            color: var(--primary-color);
            border-bottom-color: var(--primary-color);
        }
        
        .tab-content {
            display: none;
        }
        
        .tab-content.active {
            display: block;
            animation: fadeIn 0.3s ease;
        }
        
        .badge {
            display: inline-flex;
            align-items: center;
            padding: 0.25rem 0.5rem;
            border-radius: 20px;
            font-size: 0.75rem;
            font-weight: 600;
            margin-left: 0.5rem;
        }
        
        .badge-danger {
            background-color: #ffebee;
            color: var(--danger-color);
        }
        
        .badge-success {
            background-color: #e8f5e9;
            color: var(--success-color);
        }
        
        .badge-info {
            background-color: #e3f2fd;
            color: var(--info-color);
        }
        
        .empty-state {
            text-align: center;
            padding: 3rem 1rem;
            color: var(--gray-600);
        }
        
        .empty-state i {
            font-size: 3rem;
            margin-bottom: 1rem;
            color: var(--gray-400);
        }
        
        .tooltip {
            position: relative;
            display: inline-block;
            cursor: help;
        }
        
        .tooltip .tooltip-text {
            visibility: hidden;
            width: 200px;
            background-color: var(--gray-800);
            color: white;
            text-align: center;
            border-radius: 6px;
            padding: 0.5rem;
            position: absolute;
            z-index: 1;
            bottom: 125%;
            left: 50%;
            transform: translateX(-50%);
            opacity: 0;
            transition: opacity 0.3s;
        }
        
        .tooltip:hover .tooltip-text {
            visibility: visible;
            opacity: 1;
        }
        
        @media (max-width: 768px) {
            .container {
                padding: 1rem;
            }
            
            h1 {
                font-size: 2rem;
            }
            
            .tabs {
                flex-wrap: wrap;
            }
            
            .tab {
                padding: 0.5rem 1rem;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1><i class="fas fa-cube"></i> Python Package Dependency Checker</h1>
            <p>Analyze and resolve conflicts in your Python package dependencies</p>
        </header>
        
        <div class="card">
            <div class="card-header">
                Requirements Input
            </div>
            <div class="card-body">
                <p>Enter your Python package requirements below (one package per line):</p>
                <textarea id="requirementsText" placeholder="Examples:
flask==2.2.3
Werkzeug==2.2.3
numpy==1.24.2
pandas==1.5.3
..."></textarea>
                
                <div style="display: flex; gap: 10px;">
                    <button id="checkButton" class="btn-primary">
                        <i class="fas fa-check-circle btn-icon"></i> Check Dependencies
                    </button>
                    <button id="clearButton" class="btn-primary" style="background-color: var(--gray-600);">
                        <i class="fas fa-trash-alt btn-icon"></i> Clear
                    </button>
                    <button id="loadExampleButton" class="btn-primary" style="background-color: var(--info-color);">
                        <i class="fas fa-lightbulb btn-icon"></i> Load Example
                    </button>
                </div>
            </div>
        </div>
        
        <div id="loading" class="loading">
            <div class="loader"></div>
            <p style="margin-top: 1rem;">Analyzing dependencies... This might take a moment.</p>
        </div>
        
        <div id="result" class="result-section">
            <h2>Analysis Results</h2>
            
            <div id="performanceInfo" class="performance-info">
                <i class="fas fa-clock"></i>
                <span>Analysis completed in 0.5 seconds</span>
            </div>
            
            <div class="tabs">
                <div class="tab active" data-tab="conflicts">
                    <i class="fas fa-exclamation-triangle"></i> Conflicts
                    <span id="conflictsCount" class="badge badge-danger">0</span>
                </div>
                <div class="tab" data-tab="solutions">
                    <i class="fas fa-wrench"></i> Suggested Fixes
                </div>
                <div class="tab" data-tab="packages">
                    <i class="fas fa-list"></i> Packages
                    <span id="packagesCount" class="badge badge-info">0</span>
                </div>
                <div class="tab" data-tab="graph">
                    <i class="fas fa-project-diagram"></i> Dependency Graph
                </div>
            </div>
            
            <div id="conflictsTab" class="tab-content active">
                <div id="conflictsList" class="package-list">
                    <!-- Conflicts will be displayed here -->
                </div>
            </div>
            
            <div id="solutionsTab" class="tab-content">
                <div id="suggestedFixResult">
                    <p>Here's a revised requirements list that might resolve the conflicts:</p>
                    <div class="fixed-requirements">
                        <div class="fixed-requirements-header">Fixed Requirements</div>
                        <pre id="fixedRequirementsList"></pre>
                        <div class="fixed-requirements-actions">
                            <button id="copyFixedButton" class="btn-info btn-sm">
                                <i class="fas fa-copy btn-icon"></i> Copy
                            </button>
                            <button id="applyFixedButton" class="btn-success btn-sm">
                                <i class="fas fa-check btn-icon"></i> Apply Changes
                            </button>
                        </div>
                    </div>
                </div>
            </div>
            
            <div id="packagesTab" class="tab-content">
                <div id="packagesList" class="package-list">
                    <!-- Packages will be displayed here -->
                </div>
            </div>
            
            <div id="graphTab" class="tab-content">
                <div class="graph-container">
                    <p>This graph shows the relationships between your packages and their dependencies:</p>
                    <div id="graphImage"></div>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        // Tab functionality
        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', () => {
                // Remove active class from all tabs
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                
                // Add active class to clicked tab
                tab.classList.add('active');
                document.getElementById(tab.dataset.tab + 'Tab').classList.add('active');
            });
        });
        
        // Clear button
        document.getElementById('clearButton').addEventListener('click', function() {
            document.getElementById('requirementsText').value = '';
        });
        
        // Load example button
        document.getElementById('loadExampleButton').addEventListener('click', function() {
            document.getElementById('requirementsText').value = `Flask==2.2.3
Werkzeug==1.0.1  # This will conflict with Flask 2.2.3
requests==2.28.2
urllib3==2.0.3  # This will conflict with requests
pandas==1.5.3
numpy==1.20.3  # This will conflict with pandas`;
        });
        
        // Check dependencies
        document.getElementById('checkButton').addEventListener('click', function() {
            const requirementsText = document.getElementById('requirementsText').value;
            
            if (!requirementsText.trim()) {
                alert('Please enter package requirements');
                return;
            }
            
            // Show loading state
            document.getElementById('loading').style.display = 'flex';
            document.getElementById('result').style.display = 'none';
            
            // Send request to server
            const formData = new FormData();
            formData.append('requirements', requirementsText);
            
            fetch('/check_dependencies', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                // Hide loading state
                document.getElementById('loading').style.display = 'none';
                document.getElementById('result').style.display = 'block';
                
                // Display performance info
                if (data.execution_time) {
                    document.getElementById('performanceInfo').innerHTML = `
                        <i class="fas fa-clock"></i>
                        <span>Analysis completed in ${data.execution_time}</span>
                    `;
                }
                
                // Update counts
                document.getElementById('conflictsCount').textContent = data.conflicts ? data.conflicts.length : 0;
                document.getElementById('packagesCount').textContent = data.requirements ? data.requirements.length : 0;
                
                // Show the conflicts tab if conflicts exist
                if (data.conflicts && data.conflicts.length > 0) {
                    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                    document.querySelector('.tab[data-tab="conflicts"]').classList.add('active');
                    document.getElementById('conflictsTab').classList.add('active');
                }
                
                // Display conflicts
                const conflictsListEl = document.getElementById('conflictsList');
                conflictsListEl.innerHTML = '';
                
                if (data.conflicts && data.conflicts.length > 0) {
                    data.conflicts.forEach(conflict => {
                        const conflictEl = document.createElement('div');
                        conflictEl.className = `package ${conflict.type || 'conflict'}`;
                        
                        // Create conflict header
                        const headerEl = document.createElement('div');
                        headerEl.className = 'package-header';
                        
                        const nameEl = document.createElement('div');
                        nameEl.className = 'package-name';
                        nameEl.innerHTML = `<i class="fas fa-exclamation-circle" style="color: #f44336;"></i> ${conflict.package}`;
                        
                        const typeEl = document.createElement('div');
                        typeEl.className = 'package-type';
                        typeEl.textContent = conflict.type ? conflict.type.replace('_', ' ') : 'conflict';
                        
                        headerEl.appendChild(nameEl);
                        headerEl.appendChild(typeEl);
                        
                        // Create error message
                        const errorEl = document.createElement('div');
                        errorEl.className = 'error-message';
                        errorEl.textContent = conflict.error;
                        
                        conflictEl.appendChild(headerEl);
                        conflictEl.appendChild(errorEl);
                        
                        // Add suggestion if available
                        if (conflict.suggestion) {
                            const suggestionEl = document.createElement('div');
                            suggestionEl.className = 'suggestion';
                            
                            const suggestionHeaderEl = document.createElement('div');
                            suggestionHeaderEl.className = 'suggestion-header';
                            suggestionHeaderEl.innerHTML = '<i class="fas fa-lightbulb"></i> Suggestion';
                            
                            const suggestionTextEl = document.createElement('div');
                            suggestionTextEl.textContent = conflict.suggestion;
                            
                            suggestionEl.appendChild(suggestionHeaderEl);
                            suggestionEl.appendChild(suggestionTextEl);
                            
                            conflictEl.appendChild(suggestionEl);
                        }
                        
                        conflictsListEl.appendChild(conflictEl);
                    });
                } else {
                    conflictsListEl.innerHTML = `
                        <div class="empty-state">
                            <i class="fas fa-check-circle" style="color: var(--success-color);"></i>
                            <h3>All Clear!</h3>
                            <p>No conflicts detected in your requirements.</p>
                        </div>
                    `;
                }
                
                // Display packages
                const packagesListEl = document.getElementById('packagesList');
                packagesListEl.innerHTML = '';
                
                if (data.requirements && data.requirements.length > 0) {
                    // Create a list of packages analyzed with improved styling
                    packagesListEl.innerHTML = `
                        <div class="card">
                            <div class="card-body">
                                <pre>${data.requirements.join('\\n')}</pre>
                            </div>
                        </div>
                    `;
                } else {
                    packagesListEl.innerHTML = `
                        <div class="empty-state">
                            <i class="fas fa-box-open"></i>
                            <h3>No Packages</h3>
                            <p>No packages were analyzed.</p>
                        </div>
                    `;
                }
                
                // Display fixed requirements if available
                if (data.fixed_requirements && data.fixed_requirements.length > 0) {
                    document.getElementById('suggestedFixResult').style.display = 'block';
                    const fixedRequirementsListEl = document.getElementById('fixedRequirementsList');
                    fixedRequirementsListEl.textContent = data.fixed_requirements.join('\\n');
                    
                    // Copy to clipboard button
                    document.getElementById('copyFixedButton').addEventListener('click', function() {
                        navigator.clipboard.writeText(data.fixed_requirements.join('\\n'))
                            .then(() => {
                                this.innerHTML = '<i class="fas fa-check btn-icon"></i> Copied!';
                                setTimeout(() => {
                                    this.innerHTML = '<i class="fas fa-copy btn-icon"></i> Copy';
                                }, 2000);
                            })
                            .catch(err => alert('Failed to copy: ' + err));
                    });
                    
                    // Apply changes button
                    document.getElementById('applyFixedButton').addEventListener('click', function() {
                        document.getElementById('requirementsText').value = data.fixed_requirements.join('\\n');
                        
                        // Show notification
                        const notification = document.createElement('div');
                        notification.style.position = 'fixed';
                        notification.style.bottom = '20px';
                        notification.style.right = '20px';
                        notification.style.backgroundColor = '#4caf50';
                        notification.style.color = 'white';
                        notification.style.padding = '10px 20px';
                        notification.style.borderRadius = '4px';
                        notification.style.boxShadow = '0 2px 10px rgba(0, 0, 0, 0.2)';
                        notification.style.zIndex = '1000';
                        notification.innerHTML = '<i class="fas fa-check-circle"></i> Changes applied! Click "Check Dependencies" again to verify the fix.';
                        
                        document.body.appendChild(notification);
                        
                        setTimeout(() => {
                            notification.remove();
                        }, 5000);
                    });
                } else {
                    document.getElementById('suggestedFixResult').style.display = 'none';
                }
                
                // Display dependency graph
                const graphImageEl = document.getElementById('graphImage');
                graphImageEl.innerHTML = '';
                
                if (data.graph_image) {
                    const img = document.createElement('img');
                    img.src = 'data:image/png;base64,' + data.graph_image;
                    img.alt = 'Dependency Graph';
                    graphImageEl.appendChild(img);
                } else if (data.graph_error) {
                    graphImageEl.innerHTML = `
                        <div class="empty-state">
                            <i class="fas fa-exclamation-triangle" style="color: var(--warning-color);"></i>
                            <h3>Graph Generation Error</h3>
                            <p>${data.graph_error}</p>
                        </div>
                    `;
                } else {
                    graphImageEl.innerHTML = `
                        <div class="empty-state">
                            <i class="fas fa-project-diagram"></i>
                            <h3>No Graph Available</h3>
                            <p>No dependency graph could be generated.</p>
                        </div>
                    `;
                }
            })
            .catch(error => {
                document.getElementById('loading').style.display = 'none';
                
                // Show error notification
                const notification = document.createElement('div');
                notification.style.position = 'fixed';
                notification.style.bottom = '20px';
                notification.style.right = '20px';
                notification.style.backgroundColor = '#f44336';
                notification.style.color = 'white';
                notification.style.padding = '10px 20px';
                notification.style.borderRadius = '4px';
                notification.style.boxShadow = '0 2px 10px rgba(0, 0, 0, 0.2)';
                notification.style.zIndex = '1000';
                notification.innerHTML = `<i class="fas fa-exclamation-circle"></i> Error: ${error.message}`;
                
                document.body.appendChild(notification);
                
                setTimeout(() => {
                    notification.remove();
                }, 5000);
            });
        });
    </script>
</body>
</html>
        ''')
    
    app.run(debug=True)