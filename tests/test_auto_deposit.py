import unittest
from unittest.mock import Mock, patch
from requests import HTTPError

import main
from auto_deposit import build_ccxt_balance_request_variants
from main import RiskVolumeApp, _extract_cross_margin_equity, _fetch_balance_with_ccxt


class AutoDepositVariantsTests(unittest.TestCase):
    def test_supported_ccxt_exchanges_enable_server_time_adjustment(self):
        for exchange_id in ("bybit", "okx", "gate", "bitget", "mexc", "kucoin"):
            for market_type in ("spot", "futures"):
                with self.subTest(exchange=exchange_id, market=market_type):
                    variants = build_ccxt_balance_request_variants(
                        exchange_id=exchange_id,
                        market_type=market_type,
                        api_key="key",
                        api_secret="secret",
                        asset="USDT",
                    )

                    self.assertTrue(variants)
                    for variant in variants:
                        self.assertTrue(
                            variant["auth"]["options"]["adjustForTimeDifference"]
                        )

    def test_bybit_futures_uses_unified_account_fallbacks(self):
        variants = build_ccxt_balance_request_variants(
            exchange_id="bybit",
            market_type="futures",
            api_key="key",
            api_secret="secret",
            asset="USDT",
            passphrase="",
        )

        self.assertGreaterEqual(len(variants), 3)
        labels = [variant["label"] for variant in variants]
        self.assertIn("bybit-unified-swap", labels)
        self.assertIn("bybit-unified-linear", labels)

    def test_bybit_spot_keeps_spot_defaults(self):
        variants = build_ccxt_balance_request_variants(
            exchange_id="bybit",
            market_type="spot",
            api_key="key",
            api_secret="secret",
            asset="USDT",
            passphrase="",
        )

        self.assertTrue(any(variant["label"] == "bybit-spot" for variant in variants))
        spot_variant = next(variant for variant in variants if variant["label"] == "bybit-spot")
        self.assertEqual(spot_variant["auth"]["options"].get("defaultType"), "spot")
        self.assertTrue(spot_variant["auth"]["options"]["adjustForTimeDifference"])


class CrossMarginEquityTests(unittest.TestCase):
    @staticmethod
    def _time_response(server_time=1_700_000_000_000):
        response = Mock()
        response.json.return_value = {"serverTime": server_time}
        return response

    def test_bybit_endpoint_returns_wallet_balance_not_total_equity(self):
        time_response = Mock()
        time_response.json.return_value = {
            "retCode": 0,
            "time": 1_700_000_000_000,
        }
        account_response = Mock()
        account_response.json.return_value = {
            "retCode": 0,
            "result": {
                "list": [
                    {
                        "totalEquity": "102",
                        "totalWalletBalance": "100",
                    }
                ]
            },
        }
        with patch(
            "main.requests.get", side_effect=[time_response, account_response]
        ) as get:
            balance = RiskVolumeApp._fetch_bybit_unified_balance(
                None, "key", "secret", "USDT"
            )
        self.assertEqual(balance, 100.0)
        self.assertEqual(
            get.call_args_list[0].args[0],
            "https://api.bybit.com/v5/market/time",
        )
        self.assertEqual(
            get.call_args_list[1].kwargs["headers"]["X-BAPI-TIMESTAMP"],
            "1700000000000",
        )

    def test_bybit_server_time_parses_nanoseconds_fallback(self):
        response = Mock()
        response.json.return_value = {
            "retCode": 0,
            "result": {"timeNano": "1700000000123456789"},
        }
        with patch("main.requests.get", return_value=response):
            with patch("main.time.time", side_effect=[1000, 1000]):
                timestamp = main._bybit_server_timestamp_ms()
        self.assertEqual(timestamp, 1_700_000_000_123)

    def test_binance_futures_endpoint_returns_cross_wallet_balance(self):
        time_response = self._time_response()
        account_response = Mock()
        account_response.json.return_value = {
            "totalMarginBalance": "102",
            "totalCrossWalletBalance": "100",
            "totalUnrealizedProfit": "2",
        }
        with patch(
            "main.requests.get", side_effect=[time_response, account_response]
        ):
            balance = RiskVolumeApp._fetch_binance_balance_light(
                None, "key", "secret", "futures", "USDT"
            )
        self.assertEqual(balance, 100.0)

    def test_binance_futures_uses_v3_account_endpoint(self):
        time_response = self._time_response()
        account_response = Mock()
        account_response.json.return_value = {"totalCrossWalletBalance": "100"}
        with patch(
            "main.requests.get", side_effect=[time_response, account_response]
        ) as get:
            balance = RiskVolumeApp._fetch_binance_balance_light(
                None, "key", "secret", "futures", "USDT"
            )

        self.assertEqual(balance, 100.0)
        self.assertEqual(get.call_args_list[0].args[0], "https://fapi.binance.com/fapi/v1/time")
        signed_url = get.call_args_list[1].args[0]
        self.assertIn("/fapi/v3/account?", signed_url)
        self.assertIn("timestamp=1700000000", signed_url)

    def test_binance_validation_reports_api_error_without_signed_url(self):
        account_response = Mock()
        account_response.json.return_value = {
            "code": -2015,
            "msg": "Invalid API-key, IP, or permissions for action",
        }
        account_response.raise_for_status.side_effect = HTTPError(
            "400 Client Error for url: https://fapi.binance.com/fapi/v3/account?signature=secret"
        )
        time_response = self._time_response()
        app = Mock()
        app.settings = {"lang": "ru"}

        with patch(
            "main.requests.get", side_effect=[time_response, account_response]
        ):
            is_read_only, reason = RiskVolumeApp._validate_binance_read_only_key(
                app, "key", "secret", "futures"
            )

        self.assertFalse(is_read_only)
        self.assertIn("-2015", reason)
        self.assertIn("permissions", reason)
        self.assertNotIn("signature=", reason)

    def test_binance_read_only_validation_uses_restrictions_response(self):
        futures_time_response = self._time_response()
        account_response = Mock()
        account_response.json.return_value = {}
        spot_time_response = self._time_response()
        restrictions_response = Mock()
        restrictions_response.json.return_value = {
            "enableSpotAndMarginTrading": False,
            "enableMargin": False,
            "enableFutures": False,
        }
        app = Mock()
        app.settings = {"lang": "ru"}

        with patch(
            "main.requests.get",
            side_effect=[
                futures_time_response,
                account_response,
                spot_time_response,
                restrictions_response,
            ],
        ) as get:
            is_read_only, reason = RiskVolumeApp._validate_binance_read_only_key(
                app, "key", "secret", "futures"
            )

        self.assertTrue(is_read_only)
        self.assertEqual(reason, "")
        self.assertIn("/fapi/v3/account?", get.call_args_list[1].args[0])

    def test_bybit_uses_wallet_balance_without_unrealized_pnl(self):
        balance = {
            "info": {
                "result": {
                    "list": [
                        {
                            "totalEquity": "1252.50",
                            "totalWalletBalance": "1250.50",
                            "totalAvailableBalance": "400",
                        }
                    ]
                }
            }
        }
        self.assertEqual(
            _extract_cross_margin_equity("bybit", balance, "USDT"),
            1250.5,
        )

    def test_binance_uses_cross_wallet_balance_not_margin_balance(self):
        balance = {
            "info": {
                "totalMarginBalance": "102",
                "totalCrossWalletBalance": "100",
                "totalUnrealizedProfit": "2",
            }
        }
        self.assertEqual(
            _extract_cross_margin_equity("binance", balance, "USDT"),
            100.0,
        )

    def test_falls_back_to_realized_balance_by_subtracting_unrealized_pnl(self):
        balance = {
            "info": {
                "accountEquity": "102",
                "unrealizedPL": "2",
            }
        }
        self.assertEqual(
            _extract_cross_margin_equity("bitget", balance, "USDT"),
            100.0,
        )

    def test_negative_unrealized_pnl_is_removed_without_inverting_sign(self):
        balance = {
            "info": {
                "accountEquity": "98",
                "unrealisedPNL": "-2",
            }
        }
        self.assertEqual(
            _extract_cross_margin_equity("kucoin", balance, "USDT"),
            100.0,
        )

    def test_known_exchange_does_not_fall_back_to_unsafe_ccxt_total(self):
        class FakeExchange:
            def __init__(self, params):
                self.auth_params = params

            def fetch_balance(self, request_params):
                if not self.auth_params["options"]["adjustForTimeDifference"]:
                    raise AssertionError("Server-time adjustment is disabled")
                self.request_params = request_params
                return {
                    "total": {"USDT": 102},
                    "info": {"equity": "102"},
                }

            def close(self):
                pass

        fake_ccxt = type("FakeCcxt", (), {"bitget": FakeExchange})
        payload = {
            "exchange_id": "bitget",
            "api_key": "key",
            "api_secret": "secret",
            "market_type": "futures",
            "asset": "USDT",
        }
        with patch("main.importlib.import_module", return_value=fake_ccxt):
            with self.assertRaisesRegex(
                RuntimeError, "may include unrealized PnL"
            ):
                _fetch_balance_with_ccxt(payload)

    def test_falls_back_to_ccxt_total_not_free_balance(self):
        balance = {
            "free": {"USDT": 400},
            "total": {"USDT": 1250.5},
        }
        self.assertEqual(
            _extract_cross_margin_equity("unknown", balance, "USDT"),
            1250.5,
        )


if __name__ == "__main__":
    unittest.main()
