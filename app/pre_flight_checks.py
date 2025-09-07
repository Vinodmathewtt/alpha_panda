"""
Preflight health checks for startup readiness.

These checks run before services start to fail fast on critical issues
such as missing strategies, broker auth, or infrastructure problems.
"""

from datetime import datetime, time
import pytz
from typing import List, Any, Dict

from core.health import HealthCheck, HealthCheckResult
from core.database.connection import DatabaseManager
from core.database.models import StrategyConfiguration
from services.auth.service import AuthService
from services.auth.models import AuthStatus
from core.market_hours import MarketHoursChecker, MarketHoursConfig, MarketStatus
from sqlalchemy import select
from core.config.settings import Settings, Environment
from pathlib import Path
import os

try:
    from strategies.ml_utils.model_loader import ModelLoader  # optional heavy import
except Exception:
    ModelLoader = None  # type: ignore

try:
    # Optional import for feature compatibility preflight
    from strategies.core.factory import StrategyFactory as _CompositionFactory  # type: ignore
except Exception:
    _CompositionFactory = None  # type: ignore
from decimal import Decimal
from datetime import datetime as _dt
from core.schemas.events import MarketTick as _MarketTick
from core.config.settings import Environment as _Env


class InfrastructureAvailabilityCheck(HealthCheck):
    """Consolidated infra check for Postgres, Redis, and Redpanda with guidance.

    - Summarizes reachability of DB, Redis, and Redpanda in one line.
    - Adds remediation hints (make up, make bootstrap) when down.
    - In production, a failure marks the check failed; in dev/test also failed
      to stop startup, but message is more instructive.
    """

    def __init__(self, db_manager: DatabaseManager, redis_client, settings: Settings):
        self.db_manager = db_manager
        self.redis_client = redis_client
        self.settings = settings

    async def _check_db(self) -> tuple[bool, str]:
        try:
            async with self.db_manager.get_session() as session:
                from sqlalchemy import text
                await session.execute(text("SELECT 1"))
            return True, "ok"
        except Exception as e:
            return False, str(e)

    async def _check_redis(self) -> tuple[bool, str]:
        try:
            await self.redis_client.ping()
            return True, "ok"
        except Exception as e:
            return False, str(e)

    async def _check_redpanda(self) -> tuple[bool, str]:
        try:
            from aiokafka.admin import AIOKafkaAdminClient
            admin = AIOKafkaAdminClient(
                bootstrap_servers=self.settings.redpanda.bootstrap_servers,
                client_id="alpha-panda-infra-check",
            )
            try:
                await admin.start()
                await admin.describe_cluster()
                return True, "ok"
            finally:
                try:
                    await admin.close()
                except Exception:
                    pass
        except Exception as e:
            return False, str(e)

    async def check(self) -> HealthCheckResult:
        db_ok, db_msg = await self._check_db()
        rd_ok, rd_msg = await self._check_redis()
        rp_ok, rp_msg = await self._check_redpanda()

        passed = db_ok and rd_ok and rp_ok
        env = getattr(self.settings, "environment", _Env.DEVELOPMENT)
        guidance = []
        if not (db_ok and rd_ok):
            guidance.append("Bring up infra: 'make up' or 'docker compose up -d'")
        if rp_ok is False:
            guidance.append("Ensure Redpanda is up; then 'make bootstrap' for topics")

        details = {
            "postgres": {"ok": db_ok, "error": None if db_ok else db_msg},
            "redis": {"ok": rd_ok, "error": None if rd_ok else rd_msg},
            "redpanda": {"ok": rp_ok, "error": None if rp_ok else rp_msg},
            "remediation": guidance,
        }
        msg = (
            "Infrastructure OK (Postgres/Redis/Redpanda)" if passed else
            "Infrastructure unavailable: " + ", ".join([k for k, v in {
                "postgres": db_ok, "redis": rd_ok, "redpanda": rp_ok
            }.items() if not v])
        )
        return HealthCheckResult(
            component="infrastructure",
            passed=passed,
            message=msg,
            details=details,
        )

class ActiveStrategiesCheck(HealthCheck):
    """Checks if there is at least one active strategy in the database."""
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    async def check(self) -> HealthCheckResult:
        try:
            async with self.db_manager.get_session() as session:
                stmt = select(StrategyConfiguration).where(StrategyConfiguration.is_active == True)
                result = await session.execute(stmt)
                active_strategies = result.scalars().all()

                if not active_strategies:
                    return HealthCheckResult(
                        component="Strategy Config",
                        passed=False,
                        message="No active strategies found in the database. Trading cannot proceed."
                    )

                return HealthCheckResult(
                    component="Strategy Config",
                    passed=True,
                    message=f"Found {len(active_strategies)} active strategies."
                )
        except Exception as e:
            return HealthCheckResult(component="Strategy Config", passed=False, message=f"Database query failed: {e}")


class BrokerApiHealthCheck(HealthCheck):
    """
    Checks if the broker API is responsive by attempting to fetch the user profile.
    This also validates the stored access token.
    """
    def __init__(self, auth_service: AuthService):
        self.auth_service = auth_service

    async def check(self) -> HealthCheckResult:
        if not self.auth_service.is_authenticated():
            # Try to initialize authentication
            try:
                auth_initialized = await self.auth_service.auth_manager.initialize()
                if not auth_initialized:
                    # Check the specific authentication status for better error reporting
                    auth_status = self.auth_service.auth_manager.status
                    if auth_status == AuthStatus.ERROR:
                        return HealthCheckResult(
                            component="Zerodha API",
                            passed=False,
                            message="CRITICAL: Zerodha authentication configuration error. Check logs for details."
                        )
                    else:
                        return HealthCheckResult(
                            component="Zerodha API", 
                            passed=False,
                            message="CRITICAL: Zerodha authentication required but failed. System cannot start."
                        )
            except Exception as e:
                return HealthCheckResult(
                    component="Zerodha API",
                    passed=False,
                    message=f"CRITICAL: Zerodha authentication initialization failed: {e}"
                )
        try:
            profile = await self.auth_service.get_current_user_profile()
            if profile:
                return HealthCheckResult(
                    component="Zerodha API",
                    passed=True,
                    message=f"Successfully connected to broker API for user: {profile.user_shortname}."
                )
            else:
                return HealthCheckResult(
                    component="Zerodha API",
                    passed=False,
                    message="Session is active but failed to fetch user profile. Token may be invalid."
                )
        except Exception as e:
            return HealthCheckResult(component="Zerodha API", passed=False, message=f"API call failed: {e}")


class MarketHoursCheck(HealthCheck):
    """Enhanced market hours checker using the new market hours utility."""
    
    def __init__(self, config: MarketHoursConfig = None):
        """
        Initialize market hours check.
        
        Args:
            config: Market hours configuration (defaults to standard IST hours)
        """
        self.market_hours_checker = MarketHoursChecker(config)

    async def check(self) -> HealthCheckResult:
        """
        Check current market hours status.
        
        Returns comprehensive market status information as a health check result.
        """
        try:
            market_info = self.market_hours_checker.get_market_info()
            status = market_info["status"]
            
            # Create appropriate message based on status
            if status == MarketStatus.OPEN:
                message = f"Market is open for trading (Regular session: {market_info['sessions']['regular']['start']} - {market_info['sessions']['regular']['end']} IST)"
                passed = True
                
            elif status == MarketStatus.PRE_OPEN:
                message = f"Market is in pre-open session ({market_info['sessions']['pre_open']['start']} - {market_info['sessions']['pre_open']['end']} IST)"
                passed = True
                
            elif status == MarketStatus.LUNCH_BREAK:
                lunch_end = market_info['sessions'].get('lunch_break', {}).get('end', '1:30 PM')
                message = f"Market is closed for lunch break (resumes at {lunch_end} IST)"
                passed = True  # Warning only
                
            elif status == MarketStatus.WEEKEND:
                message = "Market is closed (weekend) - warning only"
                passed = True  # Warning only
                
            elif status == MarketStatus.HOLIDAY:
                message = "Market is closed (holiday) - warning only"  
                passed = True  # Warning only
                
            else:  # MarketStatus.CLOSED
                next_open = market_info.get("next_open")
                if next_open:
                    message = f"Market is closed (next open: {next_open.strftime('%Y-%m-%d %H:%M IST')}) - warning only"
                else:
                    regular_session = market_info['sessions']['regular']
                    message = f"Market is closed (outside {regular_session['start']} - {regular_session['end']} IST) - warning only"
                passed = True  # Warning only
                
            return HealthCheckResult(
                component="Market Hours",
                passed=passed,
                message=message
            )
        except Exception as e:
            return HealthCheckResult(
                component="Market Hours",
                passed=False,
                message=f"Failed to check market hours: {e}"
            )


class MLModelsPreflightCheck(HealthCheck):
    """Scan active ML strategies and verify referenced model artifacts exist.

    Policy:
    - production: fail if any required model files are missing
    - development/testing: warn-only (pass=True) with detailed message
    """

    def __init__(self, db_manager: DatabaseManager, settings: Settings):
        self.db_manager = db_manager
        self.settings = settings

    def _resolve_model_path(self, model_path: str) -> str:
        # Resolve relative paths against strategies/ directory
        if os.path.isabs(model_path):
            return model_path
        try:
            from strategies import __file__ as strategies_init  # type: ignore
            base = Path(strategies_init).resolve().parent
        except Exception:
            base = Path.cwd()
        p = Path(model_path)
        # Normalize leading 'strategies/' to avoid duplicate prefix
        if len(p.parts) > 0 and p.parts[0] == 'strategies':
            p = Path(*p.parts[1:])
        return str((base / p))

    async def check(self) -> HealthCheckResult:
        missing: Dict[str, str] = {}
        scanned = 0
        auto_fix = os.getenv("ML__AUTO_FIX_MISSING_MODELS_TO_SAMPLE", "true").lower() in ("1", "true", "yes")
        # For development reliability without extra deps, use the known bundled sample model
        SAMPLE_MODEL = "strategies/models/sample_momentum_v1.joblib"
        try:
            async with self.db_manager.get_session() as session:
                stmt = select(StrategyConfiguration).where(StrategyConfiguration.is_active == True)
                result = await session.execute(stmt)
                active = result.scalars().all()
                for cfg in active:
                    params = getattr(cfg, "parameters", {}) or {}
                    model_path = params.get("model_path")
                    if not model_path:
                        continue
                    scanned += 1
                    resolved = self._resolve_model_path(model_path)
                    if not os.path.exists(resolved):
                        missing[cfg.id] = resolved

                # In development/testing, optionally remap missing model paths to bundled sample models
                if missing and self.settings.environment != Environment.PRODUCTION and auto_fix:
                    # Choose a reasonable sample based on strategy_type
                    updated = {}
                    for cfg in active:
                        if cfg.id not in missing:
                            continue
                        # Map all missing models to the bundled sample model
                        new_path = SAMPLE_MODEL
                        # Apply update to parameters
                        p = dict(cfg.parameters or {})
                        p["model_path"] = new_path
                        cfg.parameters = p
                        session.add(cfg)
                        updated[cfg.id] = new_path
                    await session.commit()
                    # Recompute missing after auto-fix
                    missing = {}
                    for cfg in active:
                        if not getattr(cfg, "parameters", {}).get("model_path"):
                            continue
                        resolved = self._resolve_model_path(cfg.parameters["model_path"])  # type: ignore
                        if not os.path.exists(resolved):
                            missing[cfg.id] = resolved

                    if not missing:
                        return HealthCheckResult(
                            component="ML Models",
                            passed=True,
                            message=f"Auto-fixed missing models for {len(updated)} strategies (dev mode)",
                            details={"updated_model_paths": updated},
                        )

            if missing:
                msg = f"Missing ML model artifacts for {len(missing)}/{scanned} strategies"
                details = {"missing": missing, "scanned": scanned}
                # Fail fast only in production environment
                if getattr(self.settings, "environment", None) == Environment.PRODUCTION:
                    return HealthCheckResult(component="ML Models", passed=False, message=msg, details=details)
                # Dev/test: warn-only (pass=True)
                return HealthCheckResult(component="ML Models", passed=True, message=msg + " (dev warn)", details=details)

            return HealthCheckResult(component="ML Models", passed=True, message=f"All ML model artifacts present ({scanned} scanned)")
        except Exception as e:
            return HealthCheckResult(component="ML Models", passed=False, message=f"Preflight failed: {e}")


class MLFeatureCompatibilityCheck(HealthCheck):
    """Validate that ML strategy feature vector lengths match the trained model's expected input size.

    Policy:
    - production: fail if any ML strategy has a mismatch
    - development/testing: warn-only
    """

    def __init__(self, db_manager: DatabaseManager, settings: Settings):
        self.db_manager = db_manager
        self.settings = settings

    async def check(self) -> HealthCheckResult:
        # If optional deps not available, skip gracefully
        if ModelLoader is None or _CompositionFactory is None:
            return HealthCheckResult(
                component="ML Feature Compatibility",
                passed=True,
                message="Skipped (optional ML components not available)"
            )

        results: Dict[str, Dict[str, Any]] = {}
        mismatches = 0
        scanned = 0

        try:
            async with self.db_manager.get_session() as session:
                stmt = select(StrategyConfiguration).where(StrategyConfiguration.is_active == True)
                res = await session.execute(stmt)
                active = res.scalars().all()
                # Prepare factory registry
                comp = _CompositionFactory()
                registry = getattr(comp, "_processors", {})

                for cfg in active:
                    params = getattr(cfg, "parameters", {}) or {}
                    model_path = params.get("model_path")
                    if not model_path:
                        continue  # Not an ML strategy
                    scanned += 1

                    try:
                        # Build processor without triggering model load
                        factory_path = registry.get(cfg.strategy_type)
                        if not factory_path:
                            continue
                        mod_path, fn_name = factory_path.rsplit('.', 1)
                        import importlib
                        fn = getattr(importlib.import_module(mod_path), fn_name)
                        processor = fn(params)

                        # Create synthetic tick/history to infer canonical feature length
                        lookback = int(getattr(processor, 'lookback_periods', 20) or 20)
                        now = _dt.utcnow()
                        price = Decimal("100.0")
                        tick = _MarketTick(
                            instrument_token=1,
                            last_price=price,
                            timestamp=now,
                            symbol="SYNTH"
                        )
                        history = [
                            _MarketTick(
                                instrument_token=1,
                                last_price=Decimal(str(100.0 + i * 0.1)),
                                timestamp=now,
                                symbol="SYNTH",
                            ) for i in range(lookback)
                        ]
                        feats = processor.extract_features(tick, history)
                        try:
                            feature_len = int(feats.shape[-1]) if hasattr(feats, 'shape') else int(len(feats))
                        except Exception:
                            feature_len = None

                        # Load model to get expected features, if possible
                        model = ModelLoader.load_model(params.get("model_path"))
                        expected = getattr(model, 'n_features_in_', None) if model is not None else None
                        expected_int = int(expected) if expected is not None else None

                        status = "ok"
                        if expected_int is not None and (feature_len is None or feature_len != expected_int):
                            status = "mismatch"
                            mismatches += 1

                        results[cfg.id] = {
                            "expected_features": expected_int,
                            "observed_features": feature_len,
                            "strategy_type": cfg.strategy_type,
                            "status": status,
                        }
                    except Exception as ie:
                        results[cfg.id] = {
                            "error": str(ie),
                            "strategy_type": cfg.strategy_type,
                            "status": "error",
                        }

            msg = f"Scanned {scanned} ML strategies; {mismatches} mismatches"
            if getattr(self.settings, "environment", None) == Environment.PRODUCTION and mismatches > 0:
                return HealthCheckResult(
                    component="ML Feature Compatibility",
                    passed=False,
                    message=msg,
                    details={"strategies": results},
                )
            # Dev/test path: warn only
            return HealthCheckResult(
                component="ML Feature Compatibility",
                passed=True,
                message=msg + " (dev warn)",
                details={"strategies": results},
            )
        except Exception as e:
            return HealthCheckResult(
                component="ML Feature Compatibility",
                passed=False,
                message=f"Preflight failed: {e}",
            )
