"""
Hot Partition Monitoring Example

Demonstrates how to monitor message distribution across partitions
and detect hot partitions that may cause performance issues.
"""

from typing import Dict, List
from collections import defaultdict

class PartitionMetrics:
    async def check_partition_skew(self, topic: str) -> Dict[int, int]:
        """Monitor message distribution across partitions"""
        consumer = await self.create_consumer([topic], "partition_monitor")
        partition_counts = defaultdict(int)
        
        # Sample recent messages
        async for message in consumer:
            partition_counts[message.partition] += 1
            if sum(partition_counts.values()) >= 1000:  # Sample size
                break
                
        await consumer.stop()
        return dict(partition_counts)
        
    def detect_hot_partitions(self, partition_counts: Dict[int, int], threshold: float = 0.3) -> List[int]:
        """Identify partitions receiving >threshold of total traffic"""
        total_messages = sum(partition_counts.values())
        hot_partitions = []
        
        for partition, count in partition_counts.items():
            if count / total_messages > threshold:
                hot_partitions.append(partition)
                
        return hot_partitions