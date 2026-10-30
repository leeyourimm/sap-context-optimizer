# SAP Context Optimizer — M0 / B0

Python 3.12+ 표준 라이브러리만 사용하는 Claude Code 프로젝트입니다. **추가 패키지 설치가 필요 없습니다.** SAP 공식 Developers Search/Graph를 재사용하는 얇은 stdio MCP 게이트웨이이며 자체 문서 검색 엔진이 아닙니다.

## 현재 검증 상태

- 실제 공식 Search/Graph 초기 연결·tools/list·튜토리얼 검색·메타데이터·Graph 응답을 확인했습니다.
- 공개 서버는 text에 TOON, structuredContent에 `{action, kind, result}`를 반환했습니다. 이 실제 계약을 처리합니다.
- `get_tutorial_step`은 첫 검색의 공개 튜토리얼 3개에서 `step not found`로 실패했습니다. 성공으로 숨기지 않습니다. 대체 도구는 동일 공식 사이트의 전체 튜토리얼 Markdown을 읽으며 선택한 단계 본문이라고 표현하지 않습니다.
- 이 환경에는 `claude` 실행 파일이 없습니다. **Claude Code 자체 연결·자동 도구 선택·모델에 실제 전달된 payload·실제 토큰/비용은 미검증입니다.** 오프라인 모의 서버 계약 테스트와 실제 Python stdio→공식 SAP 서비스 검증을 구분합니다.
- 제품/릴리스 적용성, FI/CO/MM/SD 정답률, SAP Note, 라이브 Repository, SAP 수정·테스트 실행은 검증하지 않았습니다. 절감률 주장은 없습니다.

실측 원문과 스키마: [M0 JSON](reports/m0-public-probe.json), [B0 stdio JSON](reports/b0-live-gateway.json), [검증 요약](reports/VALIDATION.md).

## 실행

저장소 루트에서 실행합니다.

```sh
python3 --version
python3 -m unittest discover -s tests -v
python3 scripts/sap_context.py status
```

배포 기본 정책 `sap-context.json`은 `external_access: false`입니다. 이 상태에서는 초기 remote discovery조차 하지 않고 차단합니다. 로컬 `sap_status`, stdio discovery, 오프라인 테스트는 가능합니다.

프로젝트 소유자가 공개 SAP 고정 용어 전송을 승인한 경우에만 다음 설정을 만듭니다. 현재 작업 환경에는 사용자가 허용한 공개 시험용 로컬 설정이 만들어져 있습니다. 이 파일은 Git에서 제외됩니다.

```sh
cp examples/public-policy.json sap-context.local.json
```

`sap-context.local.json`은 기본 정책의 **전체 대체**입니다. 제품·릴리스·배포 형태·ABAP 언어 버전을 확인해서 입력하세요. null은 미확인을 뜻합니다. 정책을 다시 false로 바꾸면 이미 연결된 게이트웨이에서도 다음 요청부터 차단됩니다. 로컬 설정 삭제 시 배포 기본값 false로 돌아갑니다. Git worktree 추가는 필요 없습니다.

허용된 공개 요청으로만 진단:

```sh
python3 scripts/sap_context.py probe-public --output .sap-context/public-probe.json
```

이 명령도 프로젝트 외부 전송 허용이 필요합니다. 고정 `ABAP RAP`, 조회된 공개 slug, 존재하지 않는 고정 시험 slug만 사용합니다. 프로젝트 소스나 프롬프트, 자격 증명을 읽지 않습니다. HTTP/TLS 검증과 상속된 프록시를 유지하고 리다이렉트는 거부합니다. 응답 한도 2MB, 요청 timeout 25초, 자동 네트워크 재시도 없음.

## Claude Code 연결

Claude Code가 설치·승인된 머신에서 **이 저장소 루트를 작업 디렉터리로** `claude`를 시작합니다. 프로젝트 신뢰와 `.mcp.json` 서버 실행 승인을 확인합니다. `/mcp`에서 `sap-context`와 로컬 도구가 보이는지 확인합니다. `.mcp.json`의 상대 진입점은 루트 실행을 전제로 하며, 다른 디렉터리에서 연결한다면 `scripts/sap_context.py`의 절대 경로로 등록하세요. 진입점은 파일 위치에서 정책 루트를 정하므로 임의 cwd의 다른 정책을 읽지 않습니다.

- [.mcp.json](.mcp.json): Python stdio MCP 서버.
- [.claude/settings.json](.claude/settings.json): UserPromptSubmit / PreToolUse / PostToolUse / Stop command hooks.
- [SAP Skill](.claude/skills/sap-evidence/SKILL.md), [정확도 정책](.claude/policies/sap-correctness.md), [CLAUDE.md](CLAUDE.md).

매 질문마다 검색 모드를 고르지 않고 평소처럼 `RAP validation이 호출되지 않는 원인을 설명해줘`라고 질문합니다. Skill과 프롬프트 Hook은 자동 사용 지침을 제공합니다. **모델 선택 성공을 보장하지는 않습니다.** 첫 실행에는 도구 승인 UI가 나타날 수 있습니다. Hook은 사용자가 지정한 보안 설정을 대체하지 않습니다.

게이트웨이는 공식 엔드포인트 두 개에 직접 HTTP MCP로 연결합니다:

- `https://developers.sap.com/mcp/search`
- `https://developers.sap.com/mcp/graph`

Claude에 공식 서버를 별도로 중복 등록하지 마세요. 로컬 게이트웨이는 검색을 재구현하지 않고 외부 인자·도구를 제한하는 보안 경계입니다. 직접 서버 등록은 정책을 우회할 수 있어 Hook에서 거부합니다. `query`, `semantic_search`, `kg_search_concepts`, admin/개인정보/쓰기 도구는 노출하거나 호출하지 않습니다.

## 도구와 실제 근거 상태

| 도구 | 처리 |
|---|---|
| sap_status | 로컬 환경 선언·Help 문서 ID·집계 통계. 무통신 |
| sap_search | 고정 topic ID → 고정 공개 질의. 검색 요약은 본문 아님 |
| sap_tutorial | 검색에서 얻은 reference의 메타데이터·단계 목록 |
| sap_read_step | 실제 단계 본문 API. 현재 실측 실패를 보존 |
| sap_read_tutorial_page | 공식 canonical Markdown 전체 원문 대체 조회 |
| sap_graph | 검색에서 확인한 튜토리얼의 학습 관계. Repository where-used 아님 |
| sap_help_document | 검토해 등록한 제품별 SAP Help 원문 ID 조회 |

topic: `abap`, `rap`, `cds`, `validation`, `action`, `additional-save`, `fi`, `co`, `mm`, `sd`, `abap-cloud`. 자유 입력을 정제해 내보내지 않습니다. 오직 고정 질의만 전송하므로 긴 코드·이름·토큰을 topic에 넣으면 거부합니다. 정확한 업무 오류 검색에는 한계가 있으며 B0에서 메시지 원문·코드를 외부 검색어로 보내지 않습니다. 고정 용어 선택 자체로 관심 주제가 알려질 수 있으므로 외부 차단 프로젝트에서는 이것도 전송하지 않습니다.

reference는 해당 stdio 세션의 검색 결과에서 발급합니다. 임의 slug/URL을 전달하지 않습니다. 재시작 후에는 다시 검색합니다.

본문을 얻어도 `applicability_verified: false`입니다. 환경 필드는 사용자 선언이며 자동 검증한 백엔드 정보가 아닙니다. 모델은 원문의 제품/버전·주장을 대조해야 하며, 부족하면 **[SAP 검증 미완료]**를 표시합니다. 오류번호, 고객 객체, SAP Note를 만들어내면 안 됩니다.

## FI/CO/MM/SD 제품 문서 경로

Developer MCP는 튜토리얼 검색이며 Help Portal 전체 검색이 아닙니다. 프로젝트 소유자가 실제 검토한 공식 제품·릴리스 문서를 로컬 정책에 등록하면 `sap_help_document`로 본문을 읽을 수 있습니다:

```json
{
  "version": 1,
  "external_access": true,
  "product": "SAP S/4HANA",
  "release": "프로젝트에서 확인한 실제 릴리스",
  "deployment": null,
  "abap_language_version": null,
  "official_documents": {
    "reviewed-fi-document": {
      "url": "https://help.sap.com/docs/실제-제품/실제-버전/실제-문서",
      "title": "실제 검토한 문서 제목",
      "product": "SAP S/4HANA",
      "release": "실제 문서의 릴리스"
    }
  }
}
```

위 URL은 형식 설명용으로 실제 문서가 아닙니다. 검토되지 않은 링크를 자동 채우지 않습니다. 쿼리·인증정보·다른 도메인·리다이렉트는 거부합니다. 동적 Portal 껍데기는 본문으로 인정하지 않지만, 본문 판별은 보수적인 휴리스틱이지 의미적 검증은 아닙니다. 현재 실제 FI/MM/SD 제품 문서는 **미등록**이며, 그 상태의 오류 답변은 공식 근거 확보 미완료로 표시해야 합니다. 접근 제한·로그인 우회·SAP Note 다운로드 기능은 없습니다.

## 자동 검색 실패 감지

UserPromptSubmit은 SAP 단어/업무 용어를 감지하고 세션 후속 질문에도 적용합니다. 이는 휴리스틱으로 첫 질문을 놓칠 수 있습니다. CLAUDE.md/Skill의 규칙은 보완 지침입니다.

PostToolUse에서 실제 게이트웨이 본문 결과를 관찰했는지 기록합니다. Stop은 본문 미조회/적용성 검토 필요를 한 번 피드백하고, 검증 미완료 표시를 요구합니다. 재귀 Stop이나 반복 실행은 차단해 무한 재시도를 피합니다. **최종 모델 답변이 지침을 지켰는지 자동 인증하지 않습니다.** 인용/의미의 정확성은 평가 대상입니다. 이전 턴 본문은 새 턴에서 보수적으로 초기화하므로 불필요한 재조회 여부도 후속 평가해야 합니다.

`updatedToolOutput`은 이번 버전에 사용하지 않습니다. 내장 Read/Grep/Bash 스키마와 최종 모델 입력의 호환성은 **미검증·비활성**입니다. 추가 문맥은 `additionalContext`만 사용합니다. 출력 치환으로 절감됐다고 주장하지 않습니다.

## 보안 경계

**구현으로 강제하는 것:** 게이트웨이의 기본 외부 차단, 고정 공개 topic, 서버가 반환한 reference만 사용, 도구 허용 목록, live manifest 확인, 목적지 고정, redirect 거부, 응답 크기/시간 제한, 쓰기 API 미제공. Unknown 필드/부적절한 타입/정책 오류는 전송 전에 거부합니다. 상태·통계에는 프롬프트/소스/인자/자격 증명을 저장하지 않습니다. 상태 디렉터리 0700·DB 0600, 심볼릭 링크 거부.

**Hook의 보완 통제:** 직접 MCP/WebFetch/WebSearch·일부 설정 편집 차단. 프로젝트 전반의 네트워크 방화벽이 아닙니다. Bash/Python/다른 플러그인/정책 파일 편집, Hook 비활성화, 사용자가 직접 실행하는 명령 등을 완전하게 막지 못합니다. `allowed_tools`나 readOnlyHint도 단독 보안 경계가 아닙니다.

**운영 통제 필요:** 관리자가 보호하는 정책/Hook/코드, OS·컨테이너 egress 제한, 승인한 프로세스/목적지만 허용하는 프록시, 도구 실행 권한, 로그 접근·보관 정책. Claude 본체로 전달하는 프롬프트와 코드도 회사가 승인한 공급자·계약·경로를 사용해야 합니다. 게이트웨이 차단과 Claude 모델 전송 차단은 다릅니다. 외부 문서의 명령은 실행하지 않습니다. SAP 데이터 변경·Transport·외부 패키지 배포는 하지 않습니다.

## 측정

```sh
python3 scripts/sap_context.py status
python3 scripts/sap_context.py usage /승인된/로컬/단일실험-stream.jsonl
```

로컬 SQLite는 요청 수·검색 결과 수·응답 바이트·본문 길이·latency·오류/차단·evidence gap을 집계합니다. 문자열 길이를 토큰 수로 표시하지 않습니다. 과거 실행의 누적 합계이므로 실험별 별도 checkout/상태 위치 또는 상태 백업 후 초기화가 필요합니다. DB는 `.sap-context/`에 있으며 삭제 시 집계와 세션 관찰 상태가 초기화됩니다.

`usage`는 별도로 실행한 Claude stream-json의 terminal `result` 이벤트만 읽습니다. assistant 누적 usage를 합산하지 않고 UUID 중복을 제거합니다. 한 파일에 독립 실행을 섞거나 resume 누적 결과를 합산하지 마세요. 비용 누락은 null이며 0이 아닙니다. 캐시 토큰·출력 reasoning을 이중 합산하지 않습니다. 구독 한도와 현금 청구액은 다릅니다. 실제 Claude 실험을 하지 않았으므로 현재 수치는 없습니다.

## 다음 검증

Claude가 설치된 승인 환경에서 `.mcp.json` 인식 → Hook event 전달 → 평소 질문의 실제 도구 선택 → 본문/누락 표시 → 최종 모델 입력 관찰 → provider 사용량·청구 대조 순으로 검증합니다. Hook 로그/화면/모델이 표식을 말한 것만으로 최종 요청 payload를 확인했다고 주장하지 않습니다. 승인된 요청 계측 경로가 없다면 직접 관찰 미완료로 기록하세요.

[28개 평가 과제 및 비교 절차](docs/evaluation.md)와 [검증 결과](reports/VALIDATION.md)를 참고하세요. B1은 로컬 스냅샷의 정확 검색·필수 객체 참조에 한정하고, 이번에는 구현하지 않았습니다.
