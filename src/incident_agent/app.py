from .graph import build_graph
from .config import LOG_PATH, WINDOW_LINES

def main():
    graph =build_graph()

    state={
        "log_path": LOG_PATH,
        "windows_lines": WINDOW_LINES,
    }

    graph.invoke(state)


if __name__ =="__main__":
    main()