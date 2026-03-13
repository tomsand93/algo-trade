# Polymarket API Reference

**Date:** 2025-02-23
**Status:** Explored and documented

## Overview

Polymarket exposes two main public APIs:
1. **Data API** - `https://data-api.polymarket.com` - Historical trade data
2. **Gamma API** - `https://gamma-api.polymarket.com` - Market metadata

**Authentication:** Not required for public endpoints

## Data API

### Base URL
```
https://data-api.polymarket.com
```

### Endpoints

#### GET /trades
Get recent trades across all markets.

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `limit` | int | Maximum number of trades to return |
| `maker` | string (address) | Filter by wallet address (maker) |
| `start` | int (timestamp) | Start timestamp (Unix epoch) |
| `end` | int (timestamp) | End timestamp (Unix epoch) |

**Response:**
```json
[
  {
    "proxyWallet": "0x172d149ec2de59bd50c621890f635c361756a2c2",
    "side": "BUY",
    "asset": "55931182548002093027524001015559518127454854013437499344310258966867726640312",
    "conditionId": "0x17778d5cb2303bcda40f53135fad5dbfa2f7c6bb815801986c14e4729059120a",
    "size": 9.0909,
    "price": 0.99,
    "timestamp": 1771882950,
    "title": "XRP Up or Down - February 23, 4:40PM-4:45PM ET",
    "slug": "xrp-updown-5m-1771882800",
    "icon": "https://polymarket-upload.s3.us-east-2.amazonaws.com/XRP-logo.png",
    "eventSlug": "xrp-updown-5m-1771882800",
    "outcome": "Up",
    "outcomeIndex": 0,
    "transactionHash": "0x221cc25b3769a67ff90834cec0cbdf48652d3a19f7beda3b97832d842e0c780e",
    "name": "",
    "pseudonym": "",
    "bio": "",
    "profileImage": "",
    "profileImageOptimized": ""
  }
]
```

**Key Fields for Backtesting:**
- `proxyWallet` - Trader's wallet address (maker)
- `side` - "BUY" or "SELL"
- `conditionId` - Market identifier
- `size` - Trade size in USDC
- `price` - Price per share (0-1)
- `timestamp` - Unix timestamp
- `outcome` - "Yes", "No", or custom outcome
- `transactionHash` - Unique transaction identifier

## Gamma API

### Base URL
```
https://gamma-api.polymarket.com
```

### Endpoints

#### GET /markets
Get market metadata.

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `limit` | int | Maximum number of markets to return |
| `condition_id` | string | Filter by condition ID |
| `active` | boolean | Filter by active status |
| `closed` | boolean | Filter by closed status |

**Response:**
```json
[
  {
    "id": "12",
    "question": "Will Joe Biden get Coronavirus before the election?",
    "conditionId": "0xe3b423dfad8c22ff75c9899c4e8176f628cf4ad4caa00481764d320e7415f7a9",
    "slug": "will-joe-biden-get-coronavirus-before-the-election",
    "endDate": "2020-11-04T00:00:00Z",
    "category": "US-current-affairs",
    "liquidity": "0",
    "image": "...",
    "icon": "...",
    "description": "...",
    "outcomes": "[\"Yes\", \"No\"]",
    "outcomePrices": "[\"0\", \"0\"]",
    "volume": "32257.445115",
    "active": true,
    "closed": true,
    "marketType": "normal",
    "marketMakerAddress": "0x8BD6C3D7a57D650A1870dd338234f90051fe9918",
    "createdAt": "2020-10-02T16:10:01.467Z",
    "updatedAt": "2024-04-23T00:49:51.620233Z",
    "closedTime": "2020-11-02 16:31:01+00",
    "volumeNum": 32257.45,
    "liquidityNum": 0,
    "endDateIso": "2020-11-04",
    "volume24hr": 0,
    "volume1wk": 0,
    "volume1mo": 0,
    "volume1yr": 0,
    "clobTokenIds": "[\"532..."]",
    "questions": "...",
    "minPrice": "0",
    "maxPrice": "1",
    "prices": "...",
    "priceChange": "0",
    "priceChangePercentage": "0",
    "tickSize": "0.01",
    "status": "closed",
    "resolvedOutcomeId": "54..."
  }
]
```

**Key Fields for Backtesting:**
- `conditionId` - Market identifier (matches Data API)
- `question` - Market question
- `outcomes` - Array of possible outcomes
- `endDate` - When the market closes
- `active` - Whether market is still trading
- `closed` - Whether market has closed
- `resolvedOutcomeId` - The winning outcome (if resolved)
- `volumeNum` - Total trading volume
- `liquidityNum` - Current liquidity

## Data Mapping to Domain Models

### Trade (Data API) → Trade (Domain)

| Data API Field | Domain Field | Notes |
|----------------|--------------|-------|
| `proxyWallet` | `maker` | |
| `side` | `side` | "BUY" → "buy", "SELL" → "sell" |
| `conditionId` | `market_id` | |
| `size` | `size` | |
| `price` | `price` | |
| `timestamp` | `timestamp` | Convert Unix to datetime |
| `outcome` | `outcome` | |
| `transactionHash` | `transaction_hash` | |
| N/A | `taker` | Not provided by API |

### Market (Gamma API) → Market (Domain)

| Gamma API Field | Domain Field | Notes |
|-----------------|--------------|-------|
| `conditionId` | `condition_id` | |
| `question` | `question` | |
| `outcomes` | `outcomes` | Parse JSON string |
| `endDate` | `end_time` | Parse ISO datetime |
| `resolvedOutcomeId` | `resolution` | If resolved |

## Rate Limits

- No explicit rate limit headers returned
- Testing showed 20+ rapid requests succeeded
- Conservative default: 100ms delay between requests

## Notes

1. **No Authentication Required**: Both APIs are publicly accessible
2. **CORS**: APIs support cross-origin requests
3. **Timestamps**: Data API uses Unix timestamps; Gamma API uses ISO 8601
4. **Outcome Prices**: The `outcomePrices` field is a JSON string, not an array
5. **Market Resolution**: Use `status` or `resolvedOutcomeId` to determine if market is resolved

## Next Steps for Implementation

1. Create `DataAPIClient` extending `BaseHttpClient`:
   - `get_trades(maker, start, end, limit)`
   - `get_recent_trades(limit)`

2. Create `GammaAPIClient` extending `BaseHttpClient`:
   - `get_markets(limit, active, closed)`
   - `get_market(condition_id)`
   - `get_markets_by_ids(ids)`

3. Implement normalization layer to convert API responses to domain models
