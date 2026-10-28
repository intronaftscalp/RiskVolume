import copy


def build_ccxt_balance_request_variants(
    exchange_id,
    market_type,
    api_key,
    api_secret,
    asset,
    passphrase="",
):
    exchange_id = str(exchange_id or "").strip().lower()
    market_type = str(market_type or "spot").strip().lower()
    asset = str(asset or "USDT").strip().upper()

    # Timeout in ccxt is in milliseconds; use shorter timeout for faster feedback
    auth_template = {
        "apiKey": str(api_key or ""),
        "secret": str(api_secret or ""),
        "enableRateLimit": True,
        "timeout": 3000,  # 3 seconds per attempt
        "options": {"adjustForTimeDifference": True},
    }
    if passphrase:
        auth_template["password"] = str(passphrase or "")

    if exchange_id == "bybit":
        if market_type == "futures":
            return [
                {
                    "label": "bybit-unified-swap",
                    "auth": {
                        **copy.deepcopy(auth_template),
                        "options": {
                            **copy.deepcopy(auth_template["options"]),
                            "defaultType": "swap",
                        },
                    },
                    "params": {"accountType": "UNIFIED"},
                },
                {
                    "label": "bybit-unified-linear",
                    "auth": {
                        **copy.deepcopy(auth_template),
                        "options": {
                            **copy.deepcopy(auth_template["options"]),
                            "defaultType": "linear",
                        },
                    },
                    "params": {"accountType": "UNIFIED"},
                },
                {
                    "label": "bybit-unified-spot",
                    "auth": {
                        **copy.deepcopy(auth_template),
                        "options": {
                            **copy.deepcopy(auth_template["options"]),
                            "defaultType": "spot",
                        },
                    },
                    "params": {"accountType": "UNIFIED"},
                },
                {
                    "label": "bybit-futures-swap",
                    "auth": {
                        **copy.deepcopy(auth_template),
                        "options": {
                            **copy.deepcopy(auth_template["options"]),
                            "defaultType": "swap",
                        },
                    },
                    "params": {},
                },
            ]

        return [
            {
                "label": "bybit-spot",
                "auth": {
                    **copy.deepcopy(auth_template),
                    "options": {
                        **copy.deepcopy(auth_template["options"]),
                        "defaultType": "spot",
                    },
                },
                "params": {"accountType": "UNIFIED"},
            },
            {
                "label": "bybit-spot-legacy",
                "auth": {
                    **copy.deepcopy(auth_template),
                    "options": {
                        **copy.deepcopy(auth_template["options"]),
                        "defaultType": "spot",
                    },
                },
                "params": {},
            },
        ]

    options = copy.deepcopy(auth_template["options"])
    if market_type == "futures":
        default_map = {
            "bybit": "swap",
            "okx": "swap",
            "gate": "swap",
            "bitget": "swap",
            "mexc": "swap",
            "kucoin": "swap",
        }
        options["defaultType"] = default_map.get(exchange_id, "swap")

    auth = copy.deepcopy(auth_template)
    if options:
        auth["options"] = options

    return [
        {
            "label": f"{exchange_id}-{market_type}",
            "auth": auth,
            "params": {},
        }
    ]
