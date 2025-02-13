import json
from http import HTTPStatus

import httpx
from aiocache.lock import RedLock

from .._enums import CoinSymbols, QuoteSymbols
from .._mapped_ids import get_cmc_coins_ids as _get_cmc_coins_ids
from .._mapped_ids import get_cmc_quotes_ids as _get_cmc_quotes_ids
from ..cache import Cache, _get_cache_key_for_get_coin_quotes_method_params
from ..exeptions import (
    CoinNotSupportedCMC as CoinNotSupportedCMCException,
)
from ..exeptions import GetCoinQuotes as GetCoinQuotesException
from ..exeptions import (
    QuoteCoinNotSupportedCMC as QuoteCoinNotSupportedCMCException,
)
from ..response_models import CoinQuotes
from .base import BaseAPIService


class CoinMarketCapService(BaseAPIService):
    def __init__(
        self,
        api_key: str,
        cache: Cache | None = None,
        cache_ttl: int = 300,
    ) -> None:
        self._api_key = api_key
        self._cache = cache
        self._cache_ttl = cache_ttl

        self._cache_lock = None
        if self._cache is not None:
            self._cache_lock = RedLock(
                self._cache,
                key='get_coin_quotes',
                lease=20,
            )

    async def get_coin_quotes(
        self,
        coins: list[CoinSymbols],
        quotes_in: list[QuoteSymbols],
    ) -> CoinQuotes:
        if self._cache is None:
            coin_quotes: CoinQuotes = await self._get_coin_quotes(
                coins=coins, quotes_in=quotes_in
            )
        else:
            async with self._cache_lock:
                cache_key: str = (
                    _get_cache_key_for_get_coin_quotes_method_params(
                        coins=coins, quotes_in=quotes_in
                    )
                )

                if cached_value := await self._cache.get(cache_key):
                    coin_quotes = CoinQuotes.model_validate_json(cached_value)
                else:
                    coin_quotes: CoinQuotes = await self._get_coin_quotes(
                        coins=coins, quotes_in=quotes_in
                    )
                    await self._cache.set(
                        cache_key,
                        coin_quotes.model_dump_json(),
                        ttl=self._cache_ttl,
                    )

        return coin_quotes

    @staticmethod
    async def get_coin_id_by_symbol(coin_symbol: CoinSymbols) -> str:
        coin_ids = await _get_cmc_coins_ids()
        try:
            return coin_ids[coin_symbol.value]
        except KeyError:
            raise CoinNotSupportedCMCException(
                f'Coin {coin_symbol} not supported'
            ) from None

    @staticmethod
    async def get_coin_symbol_by_id(coin_id: str) -> CoinSymbols:
        coin_ids = await _get_cmc_coins_ids()
        coins = list(filter(lambda item: item[1] == coin_id, coin_ids.items()))
        if not coins:
            raise CoinNotSupportedCMCException(
                f'Coin with id {coin_id} not supported'
            )

        coin_symbol_str = coins[0][0]
        return CoinSymbols(coin_symbol_str)

    @staticmethod
    async def get_quote_id_by_symbol(
        quote_symbol: QuoteSymbols,
    ) -> str:
        quote_ids = await _get_cmc_quotes_ids()
        try:
            return quote_ids[quote_symbol.value]
        except KeyError:
            raise QuoteCoinNotSupportedCMCException(
                f'Quote {quote_symbol} not supported'
            ) from None

    @staticmethod
    async def get_quote_symbol_by_id(
        quote_id: str,
    ) -> QuoteSymbols:
        quote_ids = await _get_cmc_quotes_ids()
        coins = list(
            filter(
                lambda item: item[1] == quote_id,
                quote_ids.items(),
            )
        )
        if not coins:
            raise QuoteCoinNotSupportedCMCException(
                f'Quote with id {quote_id} not supported'
            )

        coin_symbol_str = coins[0][0]
        return QuoteSymbols(coin_symbol_str)

    async def _get_coin_quotes(
        self,
        coins: list[CoinSymbols],
        quotes_in: list[QuoteSymbols],
    ) -> CoinQuotes:
        try:
            coin_ids: list[str] = [
                await self.get_coin_id_by_symbol(coin) for coin in coins
            ]
            convert_ids: list[str] = [
                await self.get_quote_id_by_symbol(quote) for quote in quotes_in
            ]
        except CoinNotSupportedCMCException as expt:
            raise GetCoinQuotesException(str(expt)) from expt

        except QuoteCoinNotSupportedCMCException as expt:
            raise GetCoinQuotesException(str(expt)) from expt

        params = {
            'id': ','.join(coin_ids),
            'convert_id': ','.join(convert_ids),
        }

        raw_data = await self._send_request(
            path='/cryptocurrency/quotes/latest', method='get', params=params
        )
        return await CoinQuotes.from_cmc_raw_data(raw_data=raw_data)

    async def _send_request(
        self,
        path: str,
        method: str,
        params: dict | None = None,
    ) -> dict:
        if not path.startswith('/'):
            path = '/' + path  # Add leading slash to path

        headers = {
            'Accepts': 'application/json',
            'X-CMC_PRO_API_KEY': self._api_key,
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.request(
                    method=method,
                    url=(f'https://pro-api.coinmarketcap.com/v2{path}'),
                    params=params,
                    headers=headers,
                )
                json_data = response.json()

                CMC_NO_ERROR_CODE = 0
                if (
                    response.status_code == HTTPStatus.OK
                    and json_data['status']['error_code'] == CMC_NO_ERROR_CODE
                ):  # Success
                    return json_data

                raise GetCoinQuotesException(
                    f'Error retrieving coin quotes. API response: {json_data}'
                )
            except httpx.RequestError as expt:
                raise GetCoinQuotesException(
                    'Error retrieving coin quotes'
                ) from expt
            except json.JSONDecodeError as expt:
                raise GetCoinQuotesException(
                    'Error retrieving coin quotes'
                ) from expt

    def __repr__(self):
        return f"{self.__class__.__name__}(api_key='***')"
