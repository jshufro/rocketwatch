import logging
import math
from typing import Any, Dict

import circuitbreaker
import requests
from requests import HTTPError, ConnectTimeout
from retry import retry
from web3 import Web3, HTTPProvider
from web3.beacon import Beacon as Bacon

from utils.cfg import cfg

log = logging.getLogger("shared_w3")
log.setLevel(cfg["log_level"])

w3 = Web3(HTTPProvider(cfg['rocketpool.execution_layer.endpoint.current']))
mainnet_w3 = w3

if cfg['rocketpool.chain'] != "mainnet":
    mainnet_w3 = Web3(HTTPProvider(cfg['rocketpool.execution_layer.endpoint.mainnet']))

    # required for block parsing on PoA networks like goerli
    # https://web3py.readthedocs.io/en/stable/middleware.html#geth-style-proof-of-authority
    from web3.middleware import geth_poa_middleware

    w3.middleware_onion.inject(geth_poa_middleware, layer=0)

endpoints = cfg["rocketpool.consensus_layer.endpoints"]
tmp = []
for fallback_endpoint in reversed(endpoints):
    class SuperBacon(Bacon):
        def __init__(
                self,
                base_url: str,
                session: requests.Session = requests.Session(),
        ) -> None:
            super().__init__(base_url, session)

        def get_block(self, block_id: str) -> Dict[str, Any]:
            return self._make_get_request(f"/eth/v2/beacon/blocks/{block_id}")

        @retry(tries=2 if tmp else 1, exceptions=(HTTPError, ConnectionError, ConnectTimeout))
        @circuitbreaker.circuit(failure_threshold=-1 if tmp else math.inf,
                                recovery_timeout=15,
                                fallback_function=tmp[-1]._make_get_request if tmp else None)
        def _make_get_request(self, *args):
            endpoint = args[-1]
            if len(args) > 1:
                log.warning(f"falling back to {self.base_url} for request {endpoint}")
            return super()._make_get_request(endpoint)


    tmp.append(SuperBacon(fallback_endpoint))
bacon = tmp[-1]
