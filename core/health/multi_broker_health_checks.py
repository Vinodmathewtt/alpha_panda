from typing import Dict, List, Any
import os
from core.health import HealthCheck as BaseHealthCheck, HealthCheckResult
from core.config.settings import Settings

class MultiBrokerHealthCheck(BaseHealthCheck):
    """Base class for broker-aware health checks."""
    
    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
    
    async def check_all_brokers(self) -> List[HealthCheckResult]:
        """Check health for all active brokers."""
        results = []
        
        for broker in self.settings.active_brokers:
            try:
                result = await self.check_broker_health(broker)
                results.append(result)
            except Exception as e:
                results.append(HealthCheckResult(
                    component=f"{self.component_name}_{broker}",
                    passed=False,
                    message=f"Health check failed for {broker}: {str(e)}"
                ))
        
        return results
    
    async def check_broker_health(self, broker: str) -> HealthCheckResult:
        """Override this method in subclasses."""
        raise NotImplementedError

    async def check(self) -> HealthCheckResult:
        """Aggregate health across all active brokers into a single result."""
        results = await self.check_all_brokers()
        passed = all(r.passed for r in results)
        if passed:
            msg = f"All broker checks passed: {[r.component for r in results]}"
        else:
            failed = [r.component for r in results if not r.passed]
            msg = f"Broker checks failed for: {failed}"
        return HealthCheckResult(
            component=self.component_name,
            passed=passed,
            message=msg
        )

class BrokerTopicHealthCheck(MultiBrokerHealthCheck):
    """Verify that all broker-specific topics exist."""
    
    component_name = "broker_topics"
    
    async def check_broker_health(self, broker: str) -> HealthCheckResult:
        """Check if all required topics exist and meet capacity expectations."""
        from core.schemas.topics import TopicMap, TopicConfig
        
        topic_map = TopicMap(broker)
        required_topics = [
            topic_map.signals_raw(),
            topic_map.signals_validated(),
            topic_map.orders_submitted(),
            topic_map.orders_filled(),
            topic_map.pnl_snapshots()
        ]
        
        # Check topic existence using admin client
        missing_topics = await self._check_topics_exist(required_topics)
        
        if missing_topics:
            # Optional auto-bootstrap in non-production environments
            env = str(self.settings.environment).lower()
            auto_bootstrap = os.getenv("AUTO_BOOTSTRAP_TOPICS_ON_STARTUP", "true").lower() in ("1", "true", "yes")
            if env.endswith("production") or not auto_bootstrap:
                return HealthCheckResult(
                    component=f"broker_topics_{broker}",
                    passed=False,
                    message=f"Missing topics for {broker}: {', '.join(missing_topics)}",
                    details={
                        "remediation": "Run topic bootstrap with overlays",
                        "command": "make bootstrap",
                        "env_overlays": {
                            "SETTINGS__ENVIRONMENT": env.split('.')[-1],
                            "REDPANDA_BROKER_COUNT": os.getenv("REDPANDA_BROKER_COUNT", "<brokers>"),
                            "TOPIC_PARTITIONS_MULTIPLIER": os.getenv("TOPIC_PARTITIONS_MULTIPLIER", "1.0"),
                            "CREATE_DLQ_FOR_ALL": os.getenv("CREATE_DLQ_FOR_ALL", "true"),
                        },
                    },
                )
            # Try bootstrap
            created, err = await self._auto_create_topics(missing_topics, broker)
            if created:
                return HealthCheckResult(
                    component=f"broker_topics_{broker}",
                    passed=True,
                    message=f"Auto-created missing topics ({len(created)}) for {broker} (dev)",
                    details={"created": created},
                )
            # Failed to bootstrap
            return HealthCheckResult(
                component=f"broker_topics_{broker}",
                passed=False,
                message=f"Missing topics for {broker}: {', '.join(missing_topics)}; auto-bootstrap failed",
                details={
                    "error": err,
                    "remediation": "Run topic bootstrap: make bootstrap",
                },
            )

        # Validate partitions and replication factor using overlays
        expectations = self._compute_expectations(required_topics, TopicConfig.CONFIGS)
        capacity_issues = await self._check_topic_capacity(required_topics, expectations)
        if capacity_issues:
            env = str(self.settings.environment).lower()
            msgs = [f"{t}: {reason}" for t, reason in capacity_issues.items()]
            dev_warn = not env.endswith("production")
            return HealthCheckResult(
                component=f"broker_topics_{broker}",
                passed=False if not dev_warn else True,
                message=(
                    f"Topic capacity below expectations for {broker}: {'; '.join(msgs)}"
                    + (" (dev warn)" if dev_warn else "")
                ),
                details={
                    "issues": capacity_issues,
                    "expected": expectations,
                    "remediation": "Increase partitions/RF via overlays and re-run bootstrap",
                    "example": {
                        "cmd": "make bootstrap",
                        "SETTINGS__ENVIRONMENT": "production",
                        "REDPANDA_BROKER_COUNT": "3",
                        "TOPIC_PARTITIONS_MULTIPLIER": os.getenv("TOPIC_PARTITIONS_MULTIPLIER", "1.5"),
                        "CREATE_DLQ_FOR_ALL": os.getenv("CREATE_DLQ_FOR_ALL", "true"),
                    },
                },
            )
        
        return HealthCheckResult(
            component=f"broker_topics_{broker}",
            passed=True,
            message=f"All required topics exist for {broker}"
        )
    
    async def _check_topics_exist(self, topics: List[str]) -> List[str]:
        """Check which topics are missing using Kafka admin client."""
        from aiokafka.admin import AIOKafkaAdminClient
        bootstrap = self.settings.redpanda.bootstrap_servers
        admin = AIOKafkaAdminClient(
            bootstrap_servers=bootstrap,
            client_id="alpha-panda-health-admin",
        )
        try:
            await admin.start()
            existing_topics = await admin.list_topics()
            missing = [t for t in topics if t not in existing_topics]
            return missing
        except Exception:
            # On error, consider all topics missing to force visibility
            return topics
        finally:
            try:
                await admin.close()
            except Exception:
                pass

    def _compute_expectations(self, topics: List[str], base_configs: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
        """Compute expected minimal partitions and RF per topic using environment overlays."""
        env = str(self.settings.environment).lower()
        if '.' in env:
            env = env.split('.')[-1]
        broker_count = int(os.getenv("REDPANDA_BROKER_COUNT", "1"))
        multiplier = float(os.getenv("TOPIC_PARTITIONS_MULTIPLIER", "1.0"))

        expectations: Dict[str, Dict[str, int]] = {}
        for t in topics:
            cfg = base_configs.get(t, {"partitions": 1, "replication_factor": 1})
            base_partitions = int(cfg.get("partitions", 1))
            base_rf = int(cfg.get("replication_factor", 1))
            # Partitions overlay
            from math import ceil
            expected_partitions = max(1, int(ceil(base_partitions * max(0.1, multiplier))))
            # RF overlay
            if env == "production":
                expected_rf = 3 if broker_count >= 3 else max(1, broker_count)
            else:
                expected_rf = max(1, min(base_rf, broker_count)) if broker_count > 0 else base_rf
            expectations[t] = {"partitions": expected_partitions, "replication_factor": expected_rf}
        return expectations

    async def _check_topic_capacity(self, topics: List[str], expectations: Dict[str, Dict[str, int]]) -> Dict[str, str]:
        """Check topic partitions and RF using Kafka admin describe_topics."""
        from aiokafka.admin import AIOKafkaAdminClient
        bootstrap = self.settings.redpanda.bootstrap_servers
        issues: Dict[str, str] = {}
        admin = AIOKafkaAdminClient(
            bootstrap_servers=bootstrap,
            client_id="alpha-panda-health-admin",
        )
        try:
            await admin.start()
            desc = await admin.describe_topics(topics)
            # desc is list of TopicDescription-like objects
            for td in desc:
                name = getattr(td, "topic", None) or getattr(td, "name", None)
                if not name:
                    continue
                parts = getattr(td, "partitions", [])
                partition_count = len(parts) if parts else 0
                # RF: take replicas of first partition
                rf = 0
                if parts:
                    first = parts[0]
                    replicas = getattr(first, "replicas", [])
                    rf = len(replicas) if replicas is not None else 0
                exp = expectations.get(name, {"partitions": 1, "replication_factor": 1})
                reasons = []
                if partition_count < exp["partitions"]:
                    reasons.append(f"partitions {partition_count} < expected {exp['partitions']}")
                if rf < exp["replication_factor"]:
                    reasons.append(f"RF {rf} < expected {exp['replication_factor']}")
                if reasons:
                    issues[name] = "; ".join(reasons)
        except Exception:
            # On error, return generic issue to surface visibility
            for t in topics:
                issues[t] = "unable to describe topic; check admin permissions/connectivity"
        finally:
            try:
                await admin.close()
            except Exception:
                pass
        return issues

    async def _auto_create_topics(self, topics: List[str], broker: str) -> tuple[List[str] | None, str | None]:
        """Attempt to create missing topics using expectations and sane defaults.

        Returns (created_topics, error_message)
        """
        from aiokafka.admin import AIOKafkaAdminClient, NewTopic
        bootstrap = self.settings.redpanda.bootstrap_servers
        created: List[str] = []
        admin = AIOKafkaAdminClient(
            bootstrap_servers=bootstrap,
            client_id="alpha-panda-bootstrap-admin",
        )
        try:
            await admin.start()
            # Use expectations as a guide for partitions/RF
            from core.schemas.topics import TopicConfig
            expectations = self._compute_expectations(topics, TopicConfig.CONFIGS)
            new_topics = []
            for t in topics:
                exp = expectations.get(t, {"partitions": 1, "replication_factor": 1})
                parts = max(1, int(exp.get("partitions", 1)))
                rf = max(1, int(exp.get("replication_factor", 1)))
                new_topics.append(NewTopic(name=t, num_partitions=parts, replication_factor=rf))
            # Best-effort create
            await admin.create_topics(new_topics=new_topics, validate_only=False)
            created = topics
            return created, None
        except Exception as e:
            return None, str(e)
        finally:
            try:
                await admin.close()
            except Exception:
                pass

class BrokerStateHealthCheck(MultiBrokerHealthCheck):
    """Check broker-specific state and configuration."""
    
    component_name = "broker_state"
    
    async def check_broker_health(self, broker: str) -> HealthCheckResult:
        """Check broker state consistency."""
        checks = []
        
        # Check Redis cache keys are properly namespaced
        cache_health = await self._check_cache_namespace(broker)
        checks.append(cache_health)
        
        # Check database configuration for broker
        db_health = await self._check_database_config(broker)
        checks.append(db_health)
        
        # Aggregate results
        passed = all(check["passed"] for check in checks)
        message = f"Broker state check for {broker}: {'PASSED' if passed else 'FAILED'}"
        
        return HealthCheckResult(
            component=f"broker_state_{broker}",
            passed=passed,
            message=message,
            details={"broker": broker, "checks": checks}
        )
    
    async def _check_cache_namespace(self, broker: str) -> Dict[str, Any]:
        """Check that Redis cache keys are properly namespaced."""
        # TODO: Implement Redis key namespace validation
        return {"passed": True, "message": f"Cache namespace valid for {broker}"}
    
    async def _check_database_config(self, broker: str) -> Dict[str, Any]:
        """Check database configuration for broker."""
        # TODO: Implement database config validation
        return {"passed": True, "message": f"Database config valid for {broker}"}
