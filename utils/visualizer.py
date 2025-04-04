import networkx as nx
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import base64
from io import BytesIO

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