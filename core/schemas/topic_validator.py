"""
Topic validation utility for ensuring consistent broker-topic routing.
"""


class TopicValidator:
    """Validate topic routing and broker consistency"""
    
    @classmethod
    def validate_broker_topic_pair(cls, topic: str, broker: str) -> bool:
        """Validate that topic matches expected broker pattern"""
        if topic.startswith(f"{broker}."):
            return True
        
        # Check if it's a shared topic (market.ticks)
        shared_topics = ["market.ticks", "market.equity.ticks", "market.crypto.ticks"]
        if topic in shared_topics:
            return True
        
        return False
    
    @classmethod
    def get_expected_topic(cls, base_topic: str, broker: str) -> str:
        """Get expected topic name for broker"""
        shared_prefixes = ["market."]
        
        # If it's a shared topic, return as-is
        for prefix in shared_prefixes:
            if base_topic.startswith(prefix):
                return base_topic
        
        # Otherwise, add broker prefix
        if not base_topic.startswith(f"{broker}."):
            return f"{broker}.{base_topic}"
        
        return base_topic