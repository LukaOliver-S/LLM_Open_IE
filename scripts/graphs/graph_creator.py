import networkx as nx
import os
import json

class GraphCreator:
    def __init__(self, output_dir, triples_archive):
        self.output_dir = output_dir
        self.triples_archive = triples_archive
        os.makedirs(self.output_dir, exist_ok=True)

    def create_graph(self, nodes, edges, graph_name,output_format:str = "json"):
        G = nx.MultiDiGraph()
        G.add_nodes_from(nodes)
        G.add_edges_from(edges)

        if output_format == "json":
            self._save_graph_as_json(G, graph_name)
        elif output_format == "graphml":
            self._save_graph_as_graphml(G, graph_name)

    def _save_graph_as_json(self, G, graph_name):
        graph_data = nx.node_link_data(G)
        output_path = os.path.join(self.output_dir, f"{graph_name}.json")
        with open(output_path, 'w') as f:
            json.dump(graph_data, f, indent=4)
        

    def _save_graph_as_graphml(self, G, graph_name):
        output_path = os.path.join(self.output_dir, f"{graph_name}.graphml")
        nx.write_graphml(G, output_path)
        with open(output_path, 'r') as f:
            graphml_content = f.read()

    def triple_to_graph(self):
        if os.path.isfile(self.triples_archive):
            input_files = [self.triples_archive]
        elif os.path.isdir(self.triples_archive):
            input_files = [
                os.path.join(self.triples_archive, file_name)
                for file_name in os.listdir(self.triples_archive)
                if file_name.endswith((".json", ".jsonl"))
            ]
        else:
            raise FileNotFoundError(
                f"Input path does not exist: {self.triples_archive}"
            )

        for path in input_files:
            file_name = os.path.splitext(os.path.basename(path))[0]

            with open(path, "r", encoding="utf-8") as file:
                for line_number, line in enumerate(file, start=1):
                    if not line.strip():
                        continue

                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError as error:
                        raise ValueError(
                            f"Invalid JSON in {path} at line {line_number}"
                        ) from error

                    if not isinstance(item, dict):
                        continue

                    nodes = set()
                    edges = []

                    relations = item.get("gold")
                    if relations is None:
                        relations = item.get("relations", [])
                    if not isinstance(relations, list):
                        continue

                    for relation in relations:
                        if not isinstance(relation, dict):
                            continue

                        if relation.get("valid", True) is False:
                            continue

                        arg1 = str(relation.get("arg1", "")).strip()
                        rel = str(relation.get("rel", "")).strip()
                        arg2 = str(relation.get("arg2", "")).strip()

                        if not arg1 or not arg2:
                            continue

                        nodes.add(arg1)
                        nodes.add(arg2)
                        edges.append(
                            (
                                arg1,
                                arg2,
                                {"rel": rel},
                            )
                        )

                    graph_name = f"{file_name}_{line_number}"
                    self.create_graph(nodes, edges, graph_name)