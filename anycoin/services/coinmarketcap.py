import json
from http import HTTPStatus

import httpx

from .._enums import CoinSymbols
from .._mapped_ids import get_cmc_converters_ids as _get_cmc_converters_ids
from .._mapped_ids import get_cmc_crypto_ids as _get_cmc_crypto_ids
from ..exeptions import (
    ConverterCoinNotSupportedCMC as ConverterCoinNotSupportedException,
)
from ..exeptions import (
    CryptoCoinNotSupportedCMC as CryptoCoinNotSupportedException,
)
from ..exeptions import GetCoinQuotes as GetCoinQuotesException
from ..response_models import CoinQuotes
from .base import BaseAPIService


class CoinMarketCapService(BaseAPIService):
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def get_coin_quotes(
        self,
        coins: list[CoinSymbols],
        quotes_in: list[CoinSymbols],
    ) -> CoinQuotes:
        try:
            coin_ids: list[str] = [
                await self.get_crypto_id_by_coin_symbol(coin) for coin in coins
            ]
            convert_ids: list[str] = [
                await self.get_converter_id_by_coin_symbol(coin)
                for coin in quotes_in
            ]
        except CryptoCoinNotSupportedException as expt:
            raise GetCoinQuotesException(str(expt)) from expt

        except ConverterCoinNotSupportedException as expt:
            raise GetCoinQuotesException(str(expt)) from expt

        params = {
            'id': ','.join(coin_ids),
            'convert_id': ','.join(convert_ids),
        }

        raw_data = await self._send_request(
            path='/cryptocurrency/quotes/latest', method='get', params=params
        )
        return await CoinQuotes.from_cmc_raw_data(
            api_service=self, raw_data=raw_data
        )

    @staticmethod
    async def get_crypto_id_by_coin_symbol(coin_symbol: CoinSymbols) -> str:
        crypto_ids = await _get_cmc_crypto_ids()
        try:
            return crypto_ids[coin_symbol.value]
        except KeyError:
            raise CryptoCoinNotSupportedException(
                f'Crypto coin {coin_symbol} not supported'
            ) from None

    @staticmethod
    async def get_crypto_coin_symbol_by_id(crypto_id: str) -> CoinSymbols:
        crypto_ids = await _get_cmc_crypto_ids()
        coins = list(
            filter(lambda item: item[1] == crypto_id, crypto_ids.items())
        )
        if not coins:
            raise CryptoCoinNotSupportedException(
                f'Crypto with id {crypto_id} not supported'
            )

        coin_symbol_str = coins[0][0]
        return CoinSymbols(coin_symbol_str)

    @staticmethod
    async def get_converter_id_by_coin_symbol(coin_symbol: CoinSymbols) -> str:
        converter_ids = await _get_cmc_converters_ids()
        try:
            return converter_ids[coin_symbol.value]
        except KeyError:
            raise ConverterCoinNotSupportedException(
                f'Converter coin {coin_symbol} not supported'
            ) from None

    @staticmethod
    async def get_converter_coin_symbol_by_id(
        converter_id: str,
    ) -> CoinSymbols:
        converter_ids = await _get_cmc_converters_ids()
        coins = list(
            filter(
                lambda item: item[1] == converter_id,
                converter_ids.items(),
            )
        )
        if not coins:
            raise ConverterCoinNotSupportedException(
                f'Converter coin with id {converter_id} not supported'
            )

        coin_symbol_str = coins[0][0]
        return CoinSymbols(coin_symbol_str)

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
