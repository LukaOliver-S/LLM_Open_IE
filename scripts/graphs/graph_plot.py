import networkx as nx
import matplotlib.pyplot as plt
import os
import json

class GraphPlotter:
    def __init__(self, output_dir):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def plot_graph(self, graph_data, graph_name):
       if "nodes" not in graph_data and isinstance(graph_data.get("graph"), dict):
            graph_data = graph_data["graph"]
       if "nodes" not in graph_data:
            raise ValueError(
                f"{graph_name} is not a valid NetworkX graph JSON. "
                "Expected a 'nodes' field."
            )
       edge_key = "edges" if "edges" in graph_data else "links"
       G = nx.node_link_graph(graph_data, edges=edge_key)
       plt.figure(figsize=(10, 10))
       positions = nx.spring_layout(G)
       nx.draw(G, pos=positions, with_labels=True, node_size=500, node_color="skyblue", font_size=10, font_weight="bold", arrows=True, connectionstyle="arc3,rad=0.1")    
       
       edge_labels = {
           (source, target, key): data["rel"]
           for source, target, key, data in G.edges(keys=True, data=True)
           if data.get("rel")
       }

       nx.draw_networkx_edge_labels(
           G,
           pos=positions,
           edge_labels=edge_labels,
           font_size=8,
           rotate=False,
       )
       output_path = os.path.join(self.output_dir, f"{graph_name}.png")
       plt.savefig(output_path,bbox_inches='tight')
       plt.close()

    def plot_jsonl(self,input_file):
        with open(input_file, 'r', encoding='utf-8') as f:
            for line_number, line in enumerate(f, start=1):
                if not line.strip():
                    continue
                try:
                    graph_data = json.loads(line)
                    graph_name = f"{os.path.splitext(os.path.basename(input_file))[0]}_line_{line_number}"
                    self.plot_graph(graph_data, graph_name)
                except json.JSONDecodeError as error:
                    raise ValueError(
                        f"Invalid JSON in {input_file} at line {line_number}"
                    ) from error
        