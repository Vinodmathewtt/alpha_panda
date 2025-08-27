"""
Topic Configuration Class Example

Demonstrates broker-namespaced topic taxonomy for hard isolation
between paper and zerodha trading environments.
"""

from typing import Literal

Broker = Literal["paper", "zerodha"]  # Extensible for "ibkr", "fyers", etc.

class TopicMap:
    def __init__(self, broker: Broker):
        self.broker = broker
        
    def name(self, *parts: str) -> str:
        return ".".join([self.broker, *parts])
        
    def dlq_name(self, *parts: str) -> str:
        return ".".join([self.broker, *parts, "dlq"])

# Usage examples:
if __name__ == "__main__":
    paper_topics = TopicMap("paper")  
    print(paper_topics.name("orders", "filled"))     # "paper.orders.filled"
    print(paper_topics.dlq_name("orders", "filled")) # "paper.orders.filled.dlq"

    zerodha_topics = TopicMap("zerodha")
    print(zerodha_topics.name("orders", "filled"))   # "zerodha.orders.filled"