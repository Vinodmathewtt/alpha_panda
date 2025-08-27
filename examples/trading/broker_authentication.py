"""
Broker Authentication Pattern Example

Demonstrates Zerodha KiteConnect integration pattern
for broker authentication and market data access.
"""

from kiteconnect import KiteConnect, KiteTicker

class BrokerAuthenticator:
    async def get_ticker(self) -> KiteTicker:
        credentials = await self._get_broker_credentials()
        kite = KiteConnect(api_key=credentials["api_key"])
        kite.set_access_token(credentials["access_token"])
        return KiteTicker(credentials["api_key"], kite.access_token)