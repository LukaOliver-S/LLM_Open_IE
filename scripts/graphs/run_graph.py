from pathlib import Path
import json
from graph_creator import GraphCreator
from graph_plot import GraphPlotter

BASE_DIR = Path(__file__).resolve().parent.parents[1]

# Define the output directories for graphs and plots
INPUT_FILE = BASE_DIR / "Respostas"/"oiec_pt"/"10_batches"/"Respostas ExtrativoOIEC-PT"/"Grok4.0Fast.jsonl"
GRAPHS_DIR = BASE_DIR / "Outputs" / "graphs"/ "json_graphs"
PLOTS_DIR = BASE_DIR / "Outputs" / "graphs" / "plots"

def main():
    creator = GraphCreator(output_dir=GRAPHS_DIR, triples_archive=INPUT_FILE)
    creator.triple_to_graph()
    plotter = GraphPlotter(output_dir=PLOTS_DIR)
    for graph_file in GRAPHS_DIR.glob("*.json"):
        graph_data = json.loads(graph_file.read_text(encoding='utf-8'))
        graph_name = graph_file.stem
        plotter.plot_graph(graph_data, graph_name)

    print(f"Graphs and plots have been generated in {GRAPHS_DIR} and {PLOTS_DIR}.")

if __name__ == "__main__":
    main()
