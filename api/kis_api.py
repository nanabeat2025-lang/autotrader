"""
한국투자증권 KIS OpenAPI v2
- 공휴일/휴장일 확인 기능 추가
- 계좌 잔고 동기화 기능 추가
"""
import requests
from datetime import datetime
from typing import Optional


class KISApi:
    def __init__(self, app_key: str, app_secret: str, account_no: str, is_mock: bool = True):
        self.app_key = app_key
        self.app_secret = app_secret
        self.account_no = account_no
        self.is_mock = is_mock

        self.base_url = (
            "https://openapivts.koreainvestment.com:29443"
            if is_mock else
            "https://openapi.koreainvestment.com:9443"
        )
        self.access_token = None
        self.token_expires_at = None

    # ── 인증 ──────────────────────────────────────────────
    def get_access_token(self) -> str:
        if self.access_token and self.token_expires_at and datetime.now() < self.token_expires_at:
            return self.access_token
        url = f"{self.base_url}/oauth2/tokenP"
        data = {"grant_type": "client_credentials", "appkey": self.app_key, "appsecret": self.app_secret}
        resp = requests.post(url, json=data)
        resp.raise_for_status()
        result = resp.json()
        self.access_token = result["access_token"]
        from datetime import timedelta
        self.token_expires_at = datetime.now() + timedelta(seconds=int(result.get("expires_in", 86400)) - 3600)
        return self.access_token

    def _headers(self, tr_id: str) -> dict:
        return {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self.get_access_token()}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
            "custtype": "P",
        }

    # ── 공휴일/휴장일 확인 (v2 신규) ──────────────────────
    def is_holiday_today(self) -> bool:
        """오늘이 주식시장 휴장일인지 확인 (KIS API 활용)"""
        today = datetime.now().strftime("%Y%m%d")
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/chk-holiday"
        headers = self._headers("CTCA0903R")
        params = {"BASS_DT": today, "CTX_AREA_NK": "", "CTX_AREA_FK": ""}
        try:
            resp = requests.get(url, headers=headers, params=params)
            resp.raise_for_status()
            output = resp.json().get("output", [])
            for item in output:
                if item.get("bass_dt") == today:
                    return item.get("opnd_yn", "Y") == "N"  # 개장여부 N이면 휴장
        except Exception as e:
            print(f"휴장일 확인 실패 (기본값: 평일로 간주): {e}")
        # API 실패 시 토요일/일요일만 체크
        return datetime.now().weekday() >= 5

    # ── 시세 ──────────────────────────────────────────────
    def get_stock_price(self, ticker: str) -> dict:
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
        params = {"fid_cond_mrkt_div_code": "J", "fid_input_iscd": ticker}
        resp = requests.get(url, headers=self._headers("FHKST01010100"), params=params)
        resp.raise_for_status()
        return resp.json().get("output", {})

    def get_daily_ohlcv(self, ticker: str, period: int = 20) -> list[dict]:
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-daily-price"
        params = {
            "fid_cond_mrkt_div_code": "J", "fid_input_iscd": ticker,
            "fid_org_adj_prc": "0", "fid_period_div_code": "D",
        }
        resp = requests.get(url, headers=self._headers("FHKST01010400"), params=params)
        resp.raise_for_status()
        result = resp.json()

        # KIS API는 output / output1 / output2 등 다양한 키 사용
        data = result.get("output2") or result.get("output1") or result.get("output") or []
        if isinstance(data, dict):
            data = [data]
        return data[:period]

    def get_investor_trend(self, ticker: str) -> list[dict]:
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-investor"
        params = {"fid_cond_mrkt_div_code": "J", "fid_input_iscd": ticker}
        resp = requests.get(url, headers=self._headers("FHKST01010900"), params=params)
        resp.raise_for_status()
        return resp.json().get("output", [])

    def get_market_index(self) -> dict:
        result = {}
        for code, name in [("0001", "KOSPI"), ("1001", "KOSDAQ")]:
            url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-index-price"
            params = {"fid_cond_mrkt_div_code": "U", "fid_input_iscd": code}
            resp = requests.get(url, headers=self._headers("FHPUP02100000"), params=params)
            if resp.ok:
                out = resp.json().get("output", {})
                result[name] = {
                    "current": out.get("bstp_nmix_prpr", "0"),
                    "change_rate": out.get("bstp_nmix_prdy_ctrt", "0"),
                }
        return result

    def get_volume_top10(self) -> list[dict]:
        url = f"{self.base_url}/uapi/domestic-stock/v1/ranking/volume"
        params = {
            "fid_cond_mrkt_div_code": "J", "fid_cond_scr_div_code": "20171",
            "fid_input_iscd": "0000", "fid_div_cls_code": "0",
            "fid_blng_cls_code": "0", "fid_trgt_cls_code": "111111111",
            "fid_trgt_exls_cls_code": "0000000000",
            "fid_input_price_1": "", "fid_input_price_2": "",
            "fid_vol_cnt": "", "fid_input_date_1": "",
        }
        resp = requests.get(url, headers=self._headers("FHPST01710000"), params=params)
        resp.raise_for_status()
        return resp.json().get("output", [])[:10]

    # ── 계좌 / 잔고 ───────────────────────────────────────
    def get_balance(self) -> dict:
        """계좌 잔고 조회 (보유종목 + 예수금)"""
        tr_id = "VTTC8434R" if self.is_mock else "TTTC8434R"
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-balance"
        acc_no, acc_prod = self.account_no.split("-")
        params = {
            "CANO": acc_no, "ACNT_PRDT_CD": acc_prod,
            "AFHR_FLPR_YN": "N", "OFL_YN": "", "INQR_DVSN": "02",
            "UNPR_DVSN": "01", "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N", "PRCS_DVSN": "01",
            "CTX_AREA_FK100": "", "CTX_AREA_NK100": "",
        }
        resp = requests.get(url, headers=self._headers(tr_id), params=params)
        resp.raise_for_status()
        result = resp.json()
        return {"stocks": result.get("output1", []), "summary": result.get("output2", [{}])[0]}

    def sync_positions_from_broker(self) -> dict:
        """
        실제 증권 계좌에서 보유 종목을 불러와 positions.json 동기화 (v2 신규)
        수동 매매 후 불일치 방지
        """
        from core.trader import load_positions, save_positions
        balance = self.get_balance()
        broker_stocks = balance.get("stocks", [])

        synced = {}
        for item in broker_stocks:
            ticker = item.get("pdno", "")
            qty    = int(item.get("hldg_qty", 0))
            if not ticker or qty <= 0:
                continue
            avg_price = float(item.get("pchs_avg_pric", 0))
            name      = item.get("prdt_name", ticker)

            # 기존 포지션 데이터 유지 (목표가, AI 예측 등)
            existing = load_positions().get(ticker, {})
            synced[ticker] = {
                "name":         name,
                "qty":          qty,
                "buy_price":    avg_price,
                "target_price": existing.get("target_price", 0),
                "bought_at":    existing.get("bought_at", ""),
                "ai_prediction": existing.get("ai_prediction", {}),
            }

        save_positions(synced)
        print(f"✅ 계좌 동기화 완료: {len(synced)}개 종목")
        return synced

    # ── 주문 ──────────────────────────────────────────────
    def _order(self, ticker: str, qty: int, price: int, order_type: str, side: str) -> dict:
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/order-cash"
        if self.is_mock:
            tr_id = "VTTC0802U" if side == "BUY" else "VTTC0801U"
        else:
            tr_id = "TTTC0802U" if side == "BUY" else "TTTC0801U"
        acc_no, acc_prod = self.account_no.split("-")
        body = {
            "CANO": acc_no, "ACNT_PRDT_CD": acc_prod, "PDNO": ticker,
            "ORD_DVSN": order_type, "ORD_QTY": str(qty), "ORD_UNPR": str(price),
        }
        resp = requests.post(url, headers=self._headers(tr_id), json=body)
        resp.raise_for_status()
        result = resp.json()

        # KIS 응답 검증 (rt_cd: "0"=성공, 그 외=실패)
        rt_cd = result.get("rt_cd", "")
        msg   = result.get("msg1", "")
        if rt_cd == "0":
            order_no = result.get("output", {}).get("ODNO", "")
            print(f"  ✅ 주문 성공! [{side}] {ticker} {qty}주 (주문번호: {order_no})")
        else:
            print(f"  ❌ 주문 실패! [{side}] {ticker} {qty}주 → {msg}")
            raise Exception(f"주문 실패: {msg} (코드: {rt_cd})")

        return result

    def buy_market(self, ticker: str, qty: int) -> dict:
        return self._order(ticker, qty, 0, "01", "BUY")

    def sell_market(self, ticker: str, qty: int) -> dict:
        return self._order(ticker, qty, 0, "01", "SELL")
