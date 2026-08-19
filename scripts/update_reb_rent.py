#!/usr/bin/env python3
"""
한국부동산원 R-ONE 오픈API에서 "소규모 상가 임대료"(시도 단위 평균)를 가져와
data/reb_rent_by_sido.json 정적 파일로 저장한다.

배경: 이 정적 대시보드(GitHub Pages)에서 브라우저가 reb.or.kr로 직접 보내는
교차출처(cross-origin) fetch/XHR 요청은 서버 쪽에서 HTTP 503으로 차단되는 것을
확인했다(같은 순간 curl이나 top-level 페이지 이동은 정상 200 응답). 따라서
브라우저가 매번 직접 reb.or.kr을 호출하는 대신, 이 스크립트를 GitHub Actions
스케줄로 주기 실행해 결과를 저장소 안의 정적 JSON 파일로 만들어두고, 대시보드는
그 정적 파일을 같은 출처(same-origin)로 읽기만 한다.

필요 환경변수: REB_API_KEY (GitHub 저장소 Secrets에 등록 — 이 스크립트 파일이나
워크플로 파일 어디에도 실제 키 값은 저장하지 않는다).
"""
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone

STATBL_ID = "T248223134698125"  # 임대동향 지역별 임대료(2024년3분기~)_소규모 상가

# CLS_ID 500002~500018 = 17개 시도 자체를 가리키는 집계 행(같은 통계표 안에 더 잘게
# 나눈 상권 단위 행도 있지만 좌표가 없어 주소 자동 매칭이 불가능해 이번엔 제외).
SIDO_CLSID = {
    "서울특별시": 500002, "부산광역시": 500003, "대구광역시": 500004, "인천광역시": 500005,
    "광주광역시": 500006, "대전광역시": 500007, "울산광역시": 500008, "세종특별자치시": 500009,
    "경기도": 500010, "강원도": 500011, "충청북도": 500012, "충청남도": 500013,
    "전라북도": 500014, "전라남도": 500015, "경상북도": 500016, "경상남도": 500017,
    "제주특별자치도": 500018,
}


def quarter_id(base, back):
    q0 = (base.month - 1) // 3
    idx = base.year * 4 + q0 - back
    year = idx // 4
    q = idx % 4 + 1
    return f"{year}0{q}"


def fetch_json(url, retries=3):
    last_err = None
    for _ in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=20) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            last_err = e
            time.sleep(2)
    raise last_err


def main():
    key = os.environ.get("REB_API_KEY")
    if not key:
        print("REB_API_KEY 환경변수(시크릿)가 설정되어 있지 않습니다.", file=sys.stderr)
        sys.exit(1)

    now = datetime.now(timezone.utc)
    by_sido = {}
    quarter_desc = None

    for sido, cls_id in SIDO_CLSID.items():
        found = False
        for back in range(4):
            wrttime_id = quarter_id(now, back)
            url = (
                "https://www.reb.or.kr/r-one/openapi/SttsApiTblData.do"
                f"?KEY={key}&STATBL_ID={STATBL_ID}&DTACYCLE_CD=QY"
                f"&WRTTIME_IDTFR_ID={wrttime_id}&CLS_ID={cls_id}&type=json"
            )
            try:
                data = fetch_json(url)
            except Exception as e:
                print(f"[{sido}] 요청 실패: {e}", file=sys.stderr)
                continue
            result = data.get("RESULT")
            if result and result.get("CODE") == "INFO-200":
                continue  # 해당 분기 데이터 없음 -> 한 분기 더 물러남
            rows = data.get("SttsApiTblData")
            if not rows or len(rows) < 2:
                print(f"[{sido}] 예상치 못한 응답 형식: {data}", file=sys.stderr)
                continue
            row_list = rows[1].get("row") or []
            if not row_list:
                continue
            row = row_list[0]
            per_m2_thousand = row.get("DTA_VAL")
            if per_m2_thousand is None:
                continue
            per_pyeong_won = round(per_m2_thousand * 1000 * 3.305785)
            by_sido[sido] = {
                "perM2Thousand": per_m2_thousand,
                "perPyeongWon": per_pyeong_won,
            }
            if quarter_desc is None:
                quarter_desc = row.get("WRTTIME_DESC")
            found = True
            break
        if not found:
            print(f"[{sido}] 최근 4개 분기 내 데이터를 찾지 못했습니다.", file=sys.stderr)

    output = {
        "generatedAt": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "quarterDesc": quarter_desc,
        "bySido": by_sido,
    }

    os.makedirs("data", exist_ok=True)
    with open("data/reb_rent_by_sido.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"완료: {len(by_sido)}/{len(SIDO_CLSID)}개 시도 데이터 저장 ({quarter_desc})")


if __name__ == "__main__":
    main()
