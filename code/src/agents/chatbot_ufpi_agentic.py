"""UFPI scope router and compliance graph using the baseline's configured runtime."""

from rag_baseline.agentic import build_graph

# The existing agent service supplies its thread checkpointer for interrupt/resume.
# Runtime clients and the Chroma connection are created only on first invocation.
chatbot_ufpi_agentic = build_graph(interactive=True)
