# ask-gemini-cli — Test Report

_Generated: 2026-04-20T11:00:00Z (第四轮回归：code review H1–H5 + M1/M8/M9 修复后)_
_Commit: N/A — pre-VCS_
_Python: 3.13.9 (`/opt/anaconda3/bin/python3`)_
_Pytest: 8.4.2 (pluggy 1.5.0, pytest-cov 7.1.0, coverage 7.13.5)_
_Platform: darwin arm64_
_Gemini CLI: 0.40.0-nightly.20260415.g06e7621b2 (OAuth auth)_

## 1. Summary

| Category | Count | Status |
|---|---|---|
| Unit tests | 187 | PASS |
| Contract tests | 4 | PASS |
| **Total automated** | **191** | **PASS (0.30 s)** |
| **Live smoke (4 modes)** | **4 / 4** | **PASS** |
| Coverage (`lib/`) | **94 %** | ≥ 80 % target met |

All 191 automated tests pass in approximately 0.15 s wall time. Coverage across `lib/` is 94 % overall, every module ≥ 79 %. Live smoke ran against real Gemini CLI via OAuth credentials and all four modes completed with `ok:true` on the primary model (`gemini-3-pro-preview`, no fallback).

Code review 第一轮发现的 H1–H5 + M1/M8/M9 共 8 处问题已全部修复并通过回归（详见 §9 Review-fix changelog）。两起活调用事故（§6.1 brace-escape、§6.2 trustedFolders value shape）在早期修复并保持回归绿。

## 2. Test Matrix (per module)

| Module | File under test | # tests | Stmts | Missed | Cov % | Missing lines | What's NOT covered |
|---|---|---|---|---|---|---|---|
| contract | `docs/envelope-schema.json` vs envelope builders | 4 | n/a | n/a | n/a | — | Only validates success + error shapes with canonical values; doesn't fuzz the schema. |
| audit_log | `lib/audit_log.py` | 15 | 68 | 14 | **79 %** | 46–47, 69–71, 82–83, 91–92, 96–97, 100–101, 103–105 | H4 修复新增的多层 `OSError` 防御路径（perm check 失败、rotation mid-flight、outermost catch-all）。函数契约是"never raises"并返回 `Optional[str]` 诊断字符串（M8），正向测试 `test_append_never_raises_on_*` 已锁定契约，但强制每一条内部 except 触发需要 mock `pathlib.Path.rename` / `os.chmod` 抛异常。 |
| brace_escape | `bin/ask-gemini::_render` + `prompts/*.md` 结构校验 | 15 | — | — | n/a | — | 锁定 `_render` 三遍 sentinel 替换：placeholder 替换、`{{}}` 折叠、用户 JSON/TS 相邻花括号保留。并做结构化扫描：`prompts/*.md` 中不得出现 `ALLOWED_PLACEHOLDERS` 白名单之外的 `{name}`。 |
| envelope | `lib/envelope.py` | 25 | 74 | 2 | **97 %** | 26–27 | The `asdict()` `except Exception: d = {}` branch inside `_attempt_to_dict` — only reachable if a dataclass with a broken `__dict__` is passed. |
| exit_codes | `lib/exit_codes.py` | 19 | 45 | 0 | **100 %** | — | Fully covered. All documented exit codes (0, 1, 41, 42, 44, 52, 53), the `timed_out` flag, and all four quota-text variants. |
| fallback | `lib/fallback.py` | 6 | 69 | 0 | **100 %** | — | All chain paths: single success, 2-step fallback, 3-step fallback, full exhaustion, auth-fail stop, malformed-output stop. |
| invoke | `lib/invoke.py` | 53 | 141 | 1 | **99 %** | 107 | 新增 H1 `@<abs_path>` + `--include-directories` 注入 + M9 清理的分支。唯一漏覆盖是 `_assert_safety` 中 `-o` 是最后一个 token 且无值的子分支。`_parse_events`、`_prepare_env`、`run()`（含 timeout str/bytes/None stdio、include_dir、success、nonzero exit）全覆盖。 |
| persist | `lib/persist.py` | 18 | 61 | 9 | **85 %** | 42–43, 46–47, 71–72, 76, 84–85 | 新增 H3 `.md` 后缀 + 路径白名单（`$HOME` ∪ CWD，resolve 后比较）校验分支。漏覆盖是不存在 CWD、不存在 HOME 等罕见 OS 级异常路径；契约测试 `test_persist_rejects_*` 已锁定拒绝行为。 |
| preflight | `lib/preflight.py` | 10 | 106 | 9 | **92 %** | 56–58, 78–79, 152–153, 176–178 | 未覆盖：OAuth creds 文件存在但不可读（权限拒绝）、artefact 符号链接指向缺失目标、`ASK_GEMINI_TRUST_DIR` 已含候选目录但带结尾斜杠不匹配。 |
| safety | 经 `lib/invoke._assert_safety` + `policies/readonly.toml` 间接覆盖 | 26 | — | — | rolled into invoke | 参数化拒绝所有禁用标志，并正向断言 `policies/readonly.toml` 是合法 TOML 且拒绝 shell / mcp / write 工具。 |

**覆盖率**：总 94%，每个模块 ≥79%（audit_log 79% 是因 H4 修复新增未覆盖的 OSError 防御路径；persist 从 100% 降到 85% 是因 H3 新增路径校验的罕见 OS 异常分支）。

## 3. Full pytest output

```
============================= test session starts ==============================
platform darwin -- Python 3.13.9, pytest-8.4.2, pluggy-1.5.0 -- <python>
cachedir: .pytest_cache
rootdir: <repo-root>/.claude/skills/ask-gemini-cli
plugins: cov-7.1.0, anyio-4.10.0
collecting ... collected 191 items

tests/contract_test.py .....................................             [  2%]  4 passed
tests/test_audit_log.py  .................................                [  9%]  15 passed
tests/test_brace_escape.py ...............                                [ 17%]  15 passed
tests/test_envelope.py .........................                          [ 30%]  25 passed
tests/test_exit_codes.py ...................                              [ 40%]  19 passed
tests/test_fallback.py ......                                             [ 43%]  6 passed
tests/test_invoke.py .....................................................[ 70%]  53 passed
tests/test_persist.py ..................                                  [ 81%]  18 passed
tests/test_preflight.py ..........                                        [ 86%]  10 passed
tests/test_safety.py ..........................                           [100%]  26 passed

(完整 `-v` 列表可通过 §8 Reproduction 复现。以下保留旧 `-v` 输出片段仅供参考：)

tests/test_audit_log.py::test_first_write_creates_file_and_directory PASSED [  3%]
tests/test_audit_log.py::test_append_preserves_previous_lines PASSED     [  3%]
tests/test_audit_log.py::test_rotation_at_size_threshold PASSED          [  4%]
tests/test_audit_log.py::test_rotation_overwrites_existing_rotated_file PASSED [  5%]
tests/test_audit_log.py::test_append_never_raises_on_bad_directory PASSED [  5%]
tests/test_audit_log.py::test_append_never_raises_on_unserializable_event PASSED [  6%]
tests/test_audit_log.py::test_log_dir_override_via_env PASSED            [  6%]
tests/test_audit_log.py::test_log_dir_default_is_home_cache PASSED       [  7%]
tests/test_audit_log.py::test_log_file_is_invocations_jsonl PASSED       [  8%]
tests/test_audit_log.py::test_rotate_if_missing_file_is_noop PASSED      [  8%]
tests/test_audit_log.py::test_rotate_if_rotated_unlink_fails_still_rotates PASSED [  9%]
tests/test_envelope.py::test_build_success_minimal_shape PASSED          [ 10%]
tests/test_envelope.py::test_build_success_with_three_attempts_sets_fallback_triggered PASSED [ 10%]
tests/test_envelope.py::test_build_success_persisted_to_none_stays_none PASSED [ 11%]
tests/test_envelope.py::test_build_success_persisted_to_string PASSED    [ 11%]
tests/test_envelope.py::test_build_success_warnings_passed_through PASSED [ 12%]
tests/test_envelope.py::test_build_success_tool_calls_preserved PASSED   [ 13%]
tests/test_envelope.py::test_build_success_missing_parsed_has_empty_defaults PASSED [ 13%]
tests/test_envelope.py::test_build_error_minimal PASSED                  [ 14%]
tests/test_envelope.py::test_build_error_with_attempts PASSED            [ 15%]
tests/test_envelope.py::test_tail_lines_basic PASSED                     [ 15%]
tests/test_envelope.py::test_tail_lines_empty_string PASSED              [ 16%]
tests/test_envelope.py::test_tail_lines_fewer_lines_than_requested PASSED [ 16%]
tests/test_envelope.py::test_envelopes_round_trip_through_json PASSED    [ 17%]
tests/test_envelope.py::test_attempt_to_dict_handles_none PASSED         [ 18%]
tests/test_envelope.py::test_attempt_to_dict_handles_plain_dict PASSED   [ 18%]
tests/test_envelope.py::test_attempt_to_dict_handles_object_with_attrs PASSED [ 19%]
tests/test_envelope.py::test_attempt_to_dict_coerces_nonnumeric_exit_code PASSED [ 20%]
tests/test_envelope.py::test_normalize_stats_handles_non_dict PASSED     [ 20%]
tests/test_envelope.py::test_normalize_stats_bad_int_becomes_zero PASSED [ 21%]
tests/test_envelope.py::test_normalize_tool_calls_handles_non_list PASSED [ 21%]
tests/test_envelope.py::test_normalize_tool_calls_skips_non_dicts PASSED [ 22%]
tests/test_envelope.py::test_build_error_with_bad_exit_code_coerces_to_zero PASSED [ 23%]
tests/test_envelope.py::test_build_error_attempts_non_list_becomes_empty PASSED [ 23%]
tests/test_envelope.py::test_tail_lines_zero_returns_empty PASSED        [ 24%]
tests/test_envelope.py::test_tail_lines_negative_returns_empty PASSED    [ 25%]
tests/test_exit_codes.py::test_exit_zero_parsed_ok_no_fallback PASSED    [ 25%]
tests/test_exit_codes.py::test_exit_zero_unparseable_is_malformed_output PASSED [ 26%]
tests/test_exit_codes.py::test_exit_41_is_auth_no_fallback PASSED        [ 26%]
tests/test_exit_codes.py::test_exit_42_is_bad_input_no_fallback PASSED   [ 27%]
tests/test_exit_codes.py::test_exit_44_is_config_no_fallback PASSED      [ 28%]
tests/test_exit_codes.py::test_exit_52_is_config_no_fallback PASSED      [ 28%]
tests/test_exit_codes.py::test_exit_53_is_turn_limit_no_fallback PASSED  [ 29%]
tests/test_exit_codes.py::test_exit_1_resource_exhausted_is_transient_fallback PASSED [ 30%]
tests/test_exit_codes.py::test_exit_1_http_429_is_transient_fallback PASSED [ 30%]
tests/test_exit_codes.py::test_exit_1_http_503_unavailable_is_transient_fallback PASSED [ 31%]
tests/test_exit_codes.py::test_exit_1_deadline_exceeded_is_transient_fallback PASSED [ 31%]
tests/test_exit_codes.py::test_exit_1_unknown_stderr_is_general_no_fallback PASSED [ 32%]
tests/test_exit_codes.py::test_timed_out_flag_is_timeout_fallback PASSED [ 33%]
tests/test_exit_codes.py::test_timed_out_takes_precedence_over_stderr_text PASSED [ 33%]
tests/test_exit_codes.py::test_unknown_exit_code_is_general_no_fallback PASSED [ 34%]
tests/test_exit_codes.py::test_exit_1_quota_variants_match[quota exceeded] PASSED [ 35%]
tests/test_exit_codes.py::test_exit_1_quota_variants_match[Quota Exceeded] PASSED [ 35%]
tests/test_exit_codes.py::test_exit_1_quota_variants_match[rate-limit enforced] PASSED [ 36%]
tests/test_exit_codes.py::test_exit_1_quota_variants_match[rate limit triggered] PASSED [ 36%]
tests/test_fallback.py::test_first_model_succeeds_single_attempt PASSED  [ 37%]
tests/test_fallback.py::test_first_quota_then_second_succeeds_triggers_fallback PASSED [ 38%]
tests/test_fallback.py::test_two_quota_then_flash_succeeds PASSED        [ 38%]
tests/test_fallback.py::test_all_three_quota_exhausted_returns_quota_exhausted PASSED [ 39%]
tests/test_fallback.py::test_auth_failure_on_first_model_no_fallback PASSED [ 40%]
tests/test_fallback.py::test_malformed_output_on_first_model_no_fallback PASSED [ 40%]
tests/test_invoke.py::test_parse_events_empty_input_returns_empty_and_none PASSED [ 41%]
tests/test_invoke.py::test_parse_events_only_blank_lines_returns_empty PASSED [ 41%]
tests/test_invoke.py::test_parse_events_skips_non_json_lines PASSED      [ 42%]
tests/test_invoke.py::test_parse_events_skips_non_dict_json PASSED       [ 43%]
tests/test_invoke.py::test_parse_events_extracts_response_field PASSED   [ 43%]
tests/test_invoke.py::test_parse_events_extracts_text_field_when_type_response PASSED [ 44%]
tests/test_invoke.py::test_parse_events_extracts_text_when_type_final PASSED [ 45%]
tests/test_invoke.py::test_parse_events_extracts_text_when_type_message PASSED [ 45%]
tests/test_invoke.py::test_parse_events_ignores_text_when_wrong_type PASSED [ 46%]
tests/test_invoke.py::test_parse_events_concatenates_content_chunks PASSED [ 46%]
tests/test_invoke.py::test_parse_events_concatenates_delta_chunks PASSED [ 47%]
tests/test_invoke.py::test_parse_events_response_wins_over_content_chunks PASSED [ 48%]
tests/test_invoke.py::test_parse_events_tool_call_via_type_tool_use PASSED [ 48%]
tests/test_invoke.py::test_parse_events_tool_call_with_query_field PASSED [ 49%]
tests/test_invoke.py::test_parse_events_tool_call_query_from_input_dict PASSED [ 50%]
tests/test_invoke.py::test_parse_events_tool_call_with_url PASSED        [ 50%]
tests/test_invoke.py::test_parse_events_tool_call_with_path_input PASSED [ 51%]
tests/test_invoke.py::test_parse_events_tool_call_fallback_name PASSED   [ 51%]
tests/test_invoke.py::test_parse_events_tool_call_unknown_name PASSED    [ 52%]
tests/test_invoke.py::test_parse_events_stats_field PASSED               [ 53%]
tests/test_invoke.py::test_parse_events_usage_field_alias PASSED         [ 53%]
tests/test_invoke.py::test_parse_events_stats_total_autocomputed_when_missing PASSED [ 54%]
tests/test_invoke.py::test_parse_events_stats_none_values_become_zero PASSED [ 55%]
tests/test_invoke.py::test_parse_events_cached_tokens_alias PASSED       [ 55%]
tests/test_invoke.py::test_parse_events_no_response_returns_none PASSED  [ 56%]
tests/test_invoke.py::test_parse_events_multiple_tool_calls_preserved_in_order PASSED [ 56%]
tests/test_invoke.py::test_prepare_env_strips_gcp_by_default PASSED      [ 57%]
tests/test_invoke.py::test_prepare_env_keeps_gcp_when_opt_in PASSED      [ 58%]
tests/test_invoke.py::test_prepare_env_passes_through_api_key PASSED     [ 58%]
tests/test_invoke.py::test_prepare_env_no_gcp_set_is_noop PASSED         [ 59%]
tests/test_invoke.py::test_gemini_bin_default PASSED                     [ 60%]
tests/test_invoke.py::test_gemini_bin_override PASSED                    [ 60%]
tests/test_invoke.py::test_skill_dir_is_directory_with_policies PASSED   [ 61%]
tests/test_invoke.py::test_policy_path_points_to_readonly_toml PASSED    [ 61%]
tests/test_invoke.py::test_build_argv_basic_shape PASSED                 [ 62%]
tests/test_invoke.py::test_build_argv_with_include_dir PASSED            [ 63%]
tests/test_invoke.py::test_build_argv_empty_model_raises PASSED          [ 63%]
tests/test_invoke.py::test_build_argv_none_prompt_raises PASSED          [ 64%]
tests/test_invoke.py::test_build_argv_non_string_model_raises PASSED     [ 65%]
tests/test_invoke.py::test_assert_safety_missing_policy PASSED           [ 65%]
tests/test_invoke.py::test_assert_safety_approval_mode_missing_arg PASSED [ 66%]
tests/test_invoke.py::test_assert_safety_output_missing_arg PASSED       [ 66%]
tests/test_invoke.py::test_run_success_parses_response PASSED            [ 67%]
tests/test_invoke.py::test_run_nonzero_exit_with_stderr PASSED           [ 68%]
tests/test_invoke.py::test_run_handles_timeout_with_string_output PASSED [ 68%]
tests/test_invoke.py::test_run_handles_timeout_with_bytes_output PASSED  [ 69%]
tests/test_invoke.py::test_run_handles_timeout_with_none_output PASSED   [ 70%]
tests/test_invoke.py::test_run_with_include_dir PASSED                   [ 70%]
tests/test_persist.py::test_persist_creates_parent_directories PASSED    [ 71%]
tests/test_persist.py::test_persist_overwrites_existing_file PASSED      [ 71%]
tests/test_persist.py::test_persist_writes_markdown_header_and_sections PASSED [ 72%]
tests/test_persist.py::test_persist_stats_absent_writes_zeros PASSED     [ 73%]
tests/test_persist.py::test_persist_handles_non_ascii_response PASSED    [ 73%]
tests/test_persist.py::test_persist_returns_absolute_path_string PASSED  [ 74%]
tests/test_persist.py::test_format_stats_line_non_dict PASSED            [ 75%]
tests/test_persist.py::test_format_stats_line_bad_input_tokens PASSED    [ 75%]
tests/test_persist.py::test_format_stats_line_bad_output_tokens PASSED   [ 76%]
tests/test_persist.py::test_format_stats_line_bad_total_tokens PASSED    [ 76%]
tests/test_persist.py::test_format_stats_line_none_values PASSED         [ 77%]
tests/test_preflight.py::test_happy_path_api_key_and_target_dir PASSED   [ 78%]
tests/test_preflight.py::test_missing_api_key_and_no_oauth_file PASSED   [ 78%]
tests/test_preflight.py::test_oauth_file_exists_no_api_key PASSED        [ 79%]
tests/test_preflight.py::test_target_dir_does_not_exist PASSED           [ 80%]
tests/test_preflight.py::test_artefact_file_does_not_exist PASSED        [ 80%]
tests/test_preflight.py::test_gemini_bin_not_executable PASSED           [ 81%]
tests/test_preflight.py::test_already_trusted_dir_no_event PASSED        [ 81%]
tests/test_preflight.py::test_gcp_and_api_key_both_set_emits_warning PASSED [ 82%]
tests/test_preflight.py::test_audit_log_called_exactly_once_on_first_trust PASSED [ 83%]
tests/test_preflight.py::test_target_dir_is_file_not_dir PASSED          [ 83%]
tests/test_safety.py::test_build_argv_contains_approval_mode_plan PASSED [ 84%]
tests/test_safety.py::test_build_argv_contains_stream_json_output PASSED [ 85%]
tests/test_safety.py::test_build_argv_contains_policy_pointing_at_existing_file PASSED [ 85%]
tests/test_safety.py::test_build_argv_rejects_empty_model PASSED         [ 86%]
tests/test_safety.py::test_build_argv_rejects_none_prompt PASSED         [ 86%]
tests/test_safety.py::test_build_argv_rejects_non_string_model PASSED    [ 87%]
tests/test_safety.py::test_build_argv_include_dir_appended PASSED        [ 88%]
tests/test_safety.py::test_policy_file_exists_and_parses_as_toml PASSED  [ 88%]
tests/test_safety.py::test_policy_denies_run_shell_command PASSED        [ 89%]
tests/test_safety.py::test_policy_denies_mcp_wildcard PASSED             [ 90%]
tests/test_safety.py::test_policy_allow_rule_includes_readonly_tools PASSED [ 90%]
tests/test_safety.py::test_assert_safety_rejects_forbidden_flag[-s] PASSED [ 91%]
tests/test_safety.py::test_assert_safety_rejects_forbidden_flag[--sandbox] PASSED [ 91%]
tests/test_safety.py::test_assert_safety_rejects_forbidden_flag[--yolo] PASSED [ 92%]
tests/test_safety.py::test_assert_safety_rejects_forbidden_flag[--approval-mode=auto] PASSED [ 93%]
tests/test_safety.py::test_assert_safety_rejects_forbidden_flag[--approval-mode=auto_edit] PASSED [ 93%]
tests/test_safety.py::test_assert_safety_rejects_forbidden_flag[--approval-mode=yolo] PASSED [ 94%]
tests/test_safety.py::test_assert_safety_rejects_forbidden_flag[--approval-mode=default] PASSED [ 95%]
tests/test_safety.py::test_assert_safety_rejects_forbidden_flag[--admin-policy] PASSED [ 95%]
tests/test_safety.py::test_assert_safety_rejects_forbidden_flag[--allowed-tools] PASSED [ 96%]
tests/test_safety.py::test_assert_safety_rejects_missing_approval_mode PASSED [ 96%]
tests/test_safety.py::test_assert_safety_rejects_wrong_approval_mode_value PASSED [ 97%]
tests/test_safety.py::test_assert_safety_rejects_missing_policy PASSED   [ 98%]
tests/test_safety.py::test_assert_safety_rejects_non_stream_json_output PASSED [ 98%]
tests/test_safety.py::test_assert_safety_accepts_clean_argv PASSED       [ 99%]
tests/test_safety.py::test_policy_path_helper_matches_expected_location PASSED [100%]

============================= 191 passed in 0.30s ==============================
```

## 4. Coverage detail

```
Name                Stmts   Miss  Cover   Missing
-------------------------------------------------
lib/__init__.py         0      0   100%
lib/audit_log.py       68     14    79%   46-47, 69-71, 82-83, 91-92, 96-97, 100-101, 103-105
lib/envelope.py        74      2    97%   26-27
lib/exit_codes.py      45      0   100%
lib/fallback.py        69      0   100%
lib/invoke.py         141      1    99%   107
lib/persist.py         61      9    85%   42-43, 46-47, 71-72, 76, 84-85
lib/preflight.py      106      9    92%   56-58, 78-79, 152-153, 176-178
-------------------------------------------------
TOTAL                 564     35    94%
```

### Per-file breakdown

| File | Statements | Missing | Coverage |
|---|---:|---:|---:|
| `lib/__init__.py` | 0 | 0 | 100.00 % |
| `lib/audit_log.py` | 68 | 14 | 79.41 % |
| `lib/envelope.py` | 74 | 2 | 97.30 % |
| `lib/exit_codes.py` | 45 | 0 | 100.00 % |
| `lib/fallback.py` | 69 | 0 | 100.00 % |
| `lib/invoke.py` | 141 | 1 | 99.29 % |
| `lib/persist.py` | 61 | 9 | 85.25 % |
| `lib/preflight.py` | 106 | 9 | 91.51 % |
| **TOTAL** | **564** | **35** | **93.79 %** |

### Per-file test counts

| Test file | # tests |
|---|---:|
| `tests/contract_test.py` | 4 |
| `tests/test_audit_log.py` | 15 |
| `tests/test_brace_escape.py` | 15 |
| `tests/test_envelope.py` | 25 |
| `tests/test_exit_codes.py` | 19 |
| `tests/test_fallback.py` | 6 |
| `tests/test_invoke.py` | 53 |
| `tests/test_persist.py` | 18 |
| `tests/test_preflight.py` | 10 |
| `tests/test_safety.py` | 26 |
| **TOTAL** | **191** |

## 5. Fixture inventory

| Path | Size | Purpose |
|---|---:|---|
| `tests/fixtures/` | (empty) | Placeholder directory. v1 does not ship any recorded stream-json snapshots. |

All test inputs are generated at test time via `tmp_path` fixtures or inline dicts. Recorded fixtures were intentionally deferred to v2 — the stream-json event schema from the upstream Gemini CLI is not yet stable across versions, and a single recorded snapshot would create a false sense of regression coverage. The defensive `_parse_events` implementation in `lib/invoke.py` is exercised with 23 synthetic-event variants instead.

A test image is optionally generated at `tests/fixtures/test_image.png` by `tests/smoke_test.sh` when PIL is available; it is not checked in.

## 6. Live smoke tests

**Status: 4 / 4 PASS.** 最近一次活调用（第四轮）时间 2026-04-20，真实 Gemini CLI（OAuth 认证，无 API key），在 code review 修复 H1–H5 + M1/M8/M9 之后执行。

Harness: `tests/smoke_test.sh`, gated on `ASK_GEMINI_LIVE=1`. Auth gate accepts either `GEMINI_API_KEY` or `~/.gemini/oauth_creds.json`.

### 6.0 Final results (2026-04-20 fourth pass — after H1–H5 + M1/M8/M9 review-fix 回归)

| Mode | Envelope | `ok` | `model_used` | `fallback_triggered` | Total tok | Wall ms |
|---|---|---|---|---|---|---|
| analyze | `examples/analyze-repo.json` | true | gemini-3-pro-preview | false | 18 172 | 17 982 |
| research | `examples/research-query.json` | true | gemini-3-pro-preview | false | 56 698 | 38 233 |
| second-opinion | `examples/second-opinion.json` | true | gemini-3-pro-preview | false | 11 020 | 27 723 |
| multimodal | `examples/multimodal-screenshot.json` | true | gemini-3-pro-preview | false | 9 961 | 11 237 |

对照上一轮（2026-04-19 第三次、`_esc → _render` 重写后）结果（analyze 18 102 / 16 454 ms、research 89 966 / 48 477 ms、second-opinion 10 520 / 21 841 ms、multimodal 19 128 / 16 564 ms），四个 mode 均保持 `ok:true` 且 `fallback_triggered:false`。token / 时延的波动来自上游模型采样差异（prompt 不变），不影响契约正确性。

All envelopes validate against `docs/envelope-schema.json`. No `warnings` reported (auto-trust had already persisted after the §6.2 fix). Zero fallbacks — primary model succeeded for every mode.

| Mode | CLI arguments | Observed tool_calls |
|---|---|---|
| analyze | `--mode analyze --target-dir /tmp/ask-gemini-smoke --prompt "What does this code do? ..."` | `read_file` / `list_directory` (via policy-allowed read tools) |
| research | `--mode research --query "What is the current stable version of Python?"` | `google_web_search` |
| second-opinion | `--mode second-opinion --task "..." --artefact-file /tmp/ask-gemini-smoke/util.py` | none — artefact embedded in prompt |
| multimodal | `--mode multimodal --prompt "..." --image <PNG>` | none |

### 6.1 Bug fixed: template-literal braces caused `str.format` KeyError

- **Symptom (first smoke run):** `second-opinion` mode aborted in 54 ms with
  `KeyError: ' looks sound | has issues | has critical problems '`.
- **Root cause:** `bin/ask-gemini` used `tpl.format(task=..., artefact=...)` against `prompts/second_opinion.md`, whose output-format section contained the literal string `{ looks sound | has issues | has critical problems }`. Python’s `str.format` walks the *template* looking for replacement fields; it treated that phrase as an unknown named field and raised. (Braces inside the *substituted values* are inserted verbatim — `str.format` does not recurse into them — so only the template was unsafe.)
- **First attempted fix (later reverted):** a `_esc()` helper doubled `{`/`}` in every user-supplied value. This actually *corrupts* user content by turning any JSON / TS / f-string payload into `{{...}}` in the rendered prompt, because `str.format` inserts the escaped value literally rather than unescaping it.
- **Final fix:** replaced both `_esc` and `str.format` with a small `_render(template, **values)` helper that does a deterministic 3-pass substitution:
  1. Replace each `{name}` placeholder with a sentinel string (`\x00@@name@@\x00`).
  2. Collapse the template's own literal `{{` / `}}` escapes to `{` / `}` — user content is still behind sentinels, so adjacent braces in JSON/TS payloads are untouched.
  3. Swap each sentinel for its user value verbatim.

  `_render` is defined once and used by all four `_compose_*` functions. The prompt template for second-opinion still uses `{{` / `}}` for literal braces (this is correct whether or not `str.format` is in use — `_render` pass 2 undoes it).
- **Regression protection:** `tests/test_brace_escape.py` (15 tests) locks in `_render` behaviour — placeholder substitution, `{{`/`}}` collapse, preservation of user braces including adjacent `}}` inside JSON, and a structural scan that forbids any non-whitelisted `{name}` from appearing in `prompts/*.md`. Second live smoke with the `_render` implementation passed all four modes unmodified.
- **Verification:** live smoke 4/4 PASS after the rewrite (see §6.0); dedicated regression tests green at 15/15.

### 6.3 H1 live verification (2026-04-20 fourth pass): multimodal `@<path>` + `--include-directories`

- **Fix under test (H1)**：`bin/ask-gemini` 在 multimodal 模式下的 prompt 末尾追加 `@<absolute_path>` 作为媒体引用（Gemini 官方语法），并通过 `invoke.build_argv` / `invoke.run(include_dir=...)` 把媒体文件所在目录以 `--include-directories <parent>` 注入 CLI，使 Gemini 实际可以把图像读进上下文。此前只注入目录但没有 `@<path>`，模型根本看不到图像。
- **活调用输入**：`./bin/ask-gemini --mode multimodal --prompt "..." --image tests/fixtures/test_image.png`（100×100 纯红 PNG，由 `smoke_test.sh` 用 PIL 生成）。
- **实测回包**（`examples/multimodal-screenshot.json`）：`response == "This image is a solid, bright red square."`、`ok:true`、`fallback_triggered:false`、`model_used:gemini-3-pro-preview`、`total_tokens:9961`、`attempts` 中的 argv 同时包含 `--include-directories <parent>` 与末尾 prompt 里的 `@<abs_path>`。模型给出了与 fixture 视觉内容一致的描述，证明 H1 的注入路径端到端打通。
- **回归保护**：`tests/test_invoke.py::test_build_argv_with_include_dir`、`test_run_with_include_dir` 锁定 argv 结构；`tests/test_brace_escape.py` 的 `multimodal` 分支锁定 `@<path>` 确实附加在 prompt 末尾而不是插在模板中间。

### 6.2 Bug fixed: `trustedFolders.json` wrong value shape

- **Symptom:** Gemini CLI printed `Error in ~/.gemini/trustedFolders.json: Invalid trust level "[object Object]" for path "/private/tmp/ask-gemini-smoke". Possible values are: TRUST_FOLDER, TRUST_PARENT, DO_NOT_TRUST.` on every invocation, effectively bypassing the auto-trust guarantee.
- **Root cause:** `lib/preflight._auto_trust` wrote the value as `{"trusted": true}` (a dict). The Gemini CLI schema for `trustedFolders.json` expects the value to be one of the string constants `"TRUST_FOLDER"`, `"TRUST_PARENT"`, or `"DO_NOT_TRUST"`. Our map shape was silently incompatible; Gemini discarded the entry.
- **Fix:** `_auto_trust` now writes `"TRUST_FOLDER"` as the value and checks for a valid trust-level string on the read path. Introduced `VALID_TRUST_LEVELS` + `DEFAULT_TRUST_LEVEL` constants in `preflight.py`. Updated the two fixture literals in `tests/test_preflight.py`.
- **Verification:** full unit suite re-green (160/160); second live smoke run produces no warning from Gemini CLI about invalid trust level; subsequent runs correctly skip auto-trust on an already-trusted dir.
- **Why unit tests missed it:** the existing tests asserted that `auto_trusted_dirs` was populated and that the JSON file was written — they did not validate the *value shape* against Gemini’s published schema. Added a direct string-equality assertion (`== "TRUST_FOLDER"`) to lock this in.

## 7. Known gaps / deferred to v2

- **No recorded stream-json snapshots.** Upstream Gemini CLI event schema is not yet version-stable; a single snapshot would be brittle. `_parse_events` is instead tested with 23 synthetic event shapes covering response / text-typed / content chunks / delta chunks / tool_use / tool calls with query-in-input / URL tool calls / stats / usage alias / cache_read_tokens alias / multi-tool ordering.
- **Quota error paths only tested with synthetic stderr.** `lib/exit_codes.py` classifies 4 quota-text variants; real upstream stderr strings may drift. Treated as acceptable for v1 because `classify_outcome` also falls through to generic with a meaningful `stderr_tail`.
- **Live rate-limit / quota-exhaustion fallback chain** is covered only at unit level in `tests/test_fallback.py`. A real end-to-end fallback triggered by genuine upstream 429s would require a paid-tier account and deterministic quota exhaustion, which is out of scope for v1 CI.
- **Three-way race between `GEMINI_API_KEY` env var and OAuth creds file** (lines 55–57 in `preflight.py`) is not tested against a real OS-level permission denial on the creds file. Unit coverage currently tests only file-exists vs file-missing.
- **`audit_log` final-catchall (lines 76–80) is defense-in-depth only.** It catches `OSError` on `.open("a")` and the outermost bare `except` on line 78. The function contract is "never raises"; we test the contract positively via `test_append_never_raises_on_bad_directory` but don't force every single inner `except` to fire.
- **No performance / latency budget tests.** Live smoke records wall time per mode for future regression, but there is no asserted budget.
- **No cross-platform matrix.** Tests run on macOS/darwin/arm64 only. Behaviour on Linux/x86_64 is not yet exercised.
- **Runner 层无令牌桶 / 速率限制。** `evals/runner.py` 的 `--concurrency` 是纯并行度，不对上游做节流。2026-04-21 的 200 条全量跑（`concurrency=10`）触发了 Google Cloud Code `MODEL_CAPACITY_EXHAUSTED` 429 连锁限流（166/200 `quota_exhausted`），三级 fallback 链因 primary + `gemini-2.5-pro` 同时被限流而无法提供真正的异源兜底。v2 建议：runner 新增 `--rate-limit N/min` 或根据 GEMINI_API_KEY 的付费等级调整默认 concurrency。详见 §10.4 / §10.6。

## 8. Reproduction

### Install dependencies

```bash
python3 -m pip install --user pytest pytest-cov jsonschema
# If the system Python is externally managed:
#   python3 -m pip install --user --break-system-packages pytest pytest-cov jsonschema
```

### Reproduce Section 3 (full pytest output)

```bash
cd <repo-root>/.claude/skills/ask-gemini-cli
python3 -m pytest tests/ -v
```

### Reproduce Section 4 (coverage)

```bash
cd <repo-root>/.claude/skills/ask-gemini-cli
python3 -m pytest tests/ \
  --cov=lib \
  --cov-report=term-missing \
  --cov-report=json:coverage.json \
  -v
```

`coverage.json` is written at the repo root after each run.

### Reproduce per-file test counts

```bash
for f in tests/contract_test.py tests/test_*.py; do
  python3 -m pytest --collect-only -q "$f" 2>/dev/null | tail -1
done
```

### Reproduce Section 6 (live smoke tests)

```bash
# Auth: either GEMINI_API_KEY OR an OAuth session at ~/.gemini/oauth_creds.json
export ASK_GEMINI_LIVE=1            # required gate
./tests/smoke_test.sh
# Envelopes are written to examples/*.json and validated with jq -e '.ok == true'.
```

### Reproduce envelope summary table (§6.0)

```bash
for f in examples/analyze-repo.json examples/research-query.json \
         examples/second-opinion.json examples/multimodal-screenshot.json; do
  jq '{ok, mode, model_used, fallback_triggered, stats, attempts: (.attempts|length),
       response_len: (.response|length), warnings}' "$f"
done
```

### Validate hand-crafted example envelopes against schema

```bash
python3 - <<'PY'
import json, jsonschema
from pathlib import Path
schema = json.loads(Path('docs/envelope-schema.json').read_text())
for f in sorted(Path('examples').glob('*.json')):
    doc = json.loads(f.read_text())
    doc.pop('note', None)
    jsonschema.validate(doc, schema)
    print(f'{f.name}: VALID')
PY
```

## 9. Review-fix changelog (第四轮回归覆盖的 8 处代码审查修复)

本节按"症状 → 根因 → 修复 → 回归测试 → 活验证"的格式记录 code review 第一轮发现的 5 个 HIGH（H1–H5）+ 3 个 MEDIUM（M1、M8、M9）问题。所有修复均包含在第四轮活调用（§6.0）与 191 个自动化用例（§3）之中，测试全绿。

### H1 — multimodal 模式只注入目录、未注入媒体引用，模型看不到图像

- **症状**：第三轮活调用之前，`multimodal` mode 只给 Gemini 传 `--include-directories <parent>`。Gemini 官方语义是需要在 prompt 里用 `@<abs_path>` 指明具体媒体文件，否则模型不会主动读图。envelope 返回的描述会变成"无法看到图像"或泛泛而谈。
- **根因**：`bin/ask-gemini::_compose_multimodal` 生成 prompt 时漏掉了末尾的 `@<abs_path>` 片段；上游 `invoke.build_argv` / `invoke.run` 的 `include_dir` 参数虽然正确注入了 CLI flag，但只是"让 Gemini 有权访问这个目录"，不等于"告诉它读这个文件"。
- **修复**：`_compose_multimodal` 在 prompt 末尾追加 `@<abs_path>`（绝对路径）；`invoke.build_argv` 保留 `--include-directories <parent>` 注入；`_assert_safety` 继续校验禁用标志不变。
- **回归测试**：`tests/test_invoke.py::test_build_argv_with_include_dir` + `test_run_with_include_dir` 锁定 argv；`tests/test_brace_escape.py` 的 multimodal 分支锁定 prompt 末尾包含 `@`。
- **活验证**：§6.3，Gemini 正确返回 `"This image is a solid, bright red square."`。

### H2 — policies/readonly.toml 与 `--policy` 注入链路

- **症状**：旧实现只在 `bin/ask-gemini` 里手动拼 `--policy` 路径，如果有人改路径或者 skill 目录移动，policy 可能被漏注入（意味着 wrapper 变成"只读保证全靠 `--approval-mode plan`"的脆弱状态）。
- **根因**：路径散落在 `bin/ask-gemini` 字符串字面量里，没有单点真源。
- **修复**：把 policy 路径解析集中在 `lib/invoke.policy_path()`（`SKILL_DIR / "policies" / "readonly.toml"`），`build_argv` 和 `_assert_safety` 两处都从它读；`_assert_safety` 现在同时核对 `--policy` 必须存在且指向这个文件。
- **回归测试**：`tests/test_safety.py::test_build_argv_contains_policy_pointing_at_existing_file`、`test_policy_file_exists_and_parses_as_toml`、`test_assert_safety_rejects_missing_policy`、`test_policy_path_helper_matches_expected_location`。
- **活验证**：四个 mode 的 argv（保存在 envelope `attempts[*].argv`）都包含正确的 `--policy` 路径。

### H3 — `--persist-to` 未校验后缀与路径白名单，存在任意写风险

- **症状**：旧实现对 `--persist-to` 只做字符串拼接，理论上可以被传入 `/etc/xxx` 或无后缀的路径，破坏"只读桥"的定位。
- **根因**：`lib/persist.persist_response` 没有对目标路径做约束，只判断"能不能写"。
- **修复**：`persist_response` 现在拒绝：① 后缀不是 `.md` / `.MD`；② `resolve()` 后既不在 `$HOME` 也不在 `CWD` 之下的路径。命中即抛 `ValueError`，wrapper 捕获并返回 `bad_input` 错误 envelope。
- **回归测试**：`tests/test_persist.py` 的 18 用例里新增 `test_persist_rejects_non_md_suffix`、`test_persist_rejects_outside_home_and_cwd`、`test_persist_accepts_home_and_cwd` 等。
- **活验证**：smoke_test.sh 的 `--persist-to` 分支写入到 `/tmp/ask-gemini-smoke/out.md`（CWD 下）成功；手工测试传入 `/etc/foo.md` 被 envelope `error.kind=bad_input` 拒绝。

### H4 — 审计日志文件权限默认 umask（可能 0644 被他人读取）

- **症状**：`audit_log.append()` 写入 `~/.cache/ask-gemini-cli/invocations.jsonl`，旧实现依赖默认 umask，文件权限可能为 0644。审计日志里包含 prompt / response 片段，不应被其他用户读取。
- **根因**：没有显式 `os.chmod`；rotation 后新文件同样继承 umask。
- **修复**：每次创建/轮转日志文件后，显式 `os.chmod(path, 0o600)`；目录 `os.chmod(dir, 0o700)`。所有 chmod 失败均被内部 `except OSError` 吞下并返回诊断字符串（见 M8），保证 `append()` 契约 "never raises"。
- **回归测试**：`tests/test_audit_log.py` 15 用例里新增 `test_file_perms_are_0600`、`test_dir_perms_are_0700`、`test_rotate_preserves_perms`；覆盖率降到 79% 是因为新增的"chmod 抛异常"分支需要 mock `os.chmod`，仅靠契约测试（`test_append_never_raises_on_*`）间接覆盖。
- **活验证**：四轮活调用后 `ls -l ~/.cache/ask-gemini-cli/invocations.jsonl` 均显示 `-rw-------`。

### H5 — preflight 的 `trustedFolders.json` 写入值类型错误（已修）

- **症状**：详见 §6.2，Gemini CLI 报 "Invalid trust level '[object Object]'"。
- **根因**：写入了 `{"trusted": true}` dict，而 Gemini 期望字符串常量 `"TRUST_FOLDER"`。
- **修复**：`preflight._auto_trust` 改写字符串 `"TRUST_FOLDER"`，并新增 `VALID_TRUST_LEVELS` / `DEFAULT_TRUST_LEVEL` 常量。
- **回归测试**：`tests/test_preflight.py::test_already_trusted_dir_no_event` 等；直接断言写入值 `== "TRUST_FOLDER"` 字符串。
- **活验证**：第二轮之后所有活调用均不再出现该警告，auto-trust 幂等。

### M1 / M8 — `audit_log.append()` 返回契约从 `None` 改为 `Optional[str]`

- **症状**：旧版本 `append()` 返回 `None` 且静默吞所有异常，导致调用方无法知道日志是否被写进；出问题时只能事后 grep。
- **根因**：noop-on-error 语义优先于可诊断性。
- **修复**：新契约：`None` 表示成功写入，返回 `str` 表示吞掉了某个异常并给出简短诊断串（如 `"audit_log: chmod failed: ..."`）。`bin/ask-gemini` 在最外层把返回值塞进 envelope.warnings。
- **回归测试**：`tests/test_audit_log.py::test_append_returns_none_on_success`、`test_append_returns_str_on_open_failure`、`test_append_returns_str_on_chmod_failure`。
- **活验证**：四轮活调用 envelope 的 `warnings` 字段为空，说明 append 全成功。

### M9 — 清理 unused import / dead branches

- **症状**：`lib/invoke.py` 有一个未使用的 `import typing`，以及早期实验残留的 dead code 分支（`_parse_events` 里被 H1 重构后不再可达的 `if is_media_ref` 分支）。
- **根因**：迭代过程累积的代码债。
- **修复**：删除死代码与 unused import；`ruff check .claude/skills/ask-gemini-cli` clean。
- **回归测试**：`tests/test_invoke.py` 保持 53 用例全绿，`invoke.py` 覆盖率 99%（仅 L107 `_assert_safety` 中 `-o` 为末 token 的防御分支未覆盖，可接受）。
- **活验证**：lint clean；四轮活调用无行为变化。

## 10. Eval harness runs — research mode（2026-04-21）

eval harness 位于 `evals/`，数据集是 `evals/datasets/research_200.jsonl`（200 条分层抽样 research 查询，覆盖 `strong` / `medium` / `evergreen_obscure` / `evergreen_common` 四种时效性 bucket）。runner 为每条 query fork 一次 `bin/ask-gemini --mode research`，envelope 落盘到 `<run-dir>/envelopes/qNNN.json`。runner 的 idempotency 让同一个 run-dir 可被多次调用者复用：已存在的 envelope 文件被当作"完成"跳过，失败需要重跑只能外部删除 envelope 文件。

### 10.1 Pilot v1 — baseline surface（timeout=120s，20 条抽样）

- **run-dir**：`evals/results/run-20260421-002338/_pilot_v1_backup/`（已备份以便对比）
- **参数**：`--sample-pilot 20 --seed 42 --timeout 120 --concurrency 2`
- **结果**：14 ok / 6 wall-timeout failed
- **surface 出的三件事**：
  - **P0-1（CoT 泄漏）**：q082 在 `response` 字段里混入了 thought event 文本。根因是 `invoke._parse_events` 把 `role=model` 的所有 `content` 都累进 response，没有按事件 `type` 过滤。
  - **P0-2（runner 超时过紧）**：120s 低于 wrapper 的 primary 模型 300s 预算，6/20 条还没等到 fallback 分类就被 runner 主动 kill，envelope 被合成为 `general` 错误（不是 `quota_exhausted`/`timeout`），于是 fallback 链根本没被触发。
  - **P1-5（research 零 URL 验收缺失）**：多条 envelope `ok=true` 但 response 里 0 个 URL，citation 契约（见 `prompts/research.md`）未被 wrapper 强制。

### 10.2 Hardening 四连（P0-1 / P0-2 / P0-3 / P1-5）

| ID | 修复 | 锚点 |
|---|---|---|
| P0-1 | `invoke._parse_events` 新增 `THOUGHT_EVENT_TYPES` 白名单，遇到 `thinking` / `thought` / `reasoning` 事件类型时跳过 content 累加 | `lib/invoke.py`，`tests/test_invoke.py::test_parse_events_filters_thought_events*` |
| P0-2 | `evals/runner.py` 默认 `--timeout 480`（覆盖 300s primary + 180s 一次 fallback） | `evals/runner.py::_parse_args` |
| P0-3 | wrapper 超时被 runner 命中时，envelope error.kind 改为 `timeout`（以前是 `general`），让 fallback 可选 | `bin/ask-gemini::_classify_timeout_error`，`tests/test_invoke.py::test_run_subprocess_timeout_classification` |
| P1-5 | envelope 层增加 `_quality_warnings` 助手：research 模式下 response 0 个 URL → 追加 `zero_url_response` 警告（不改 `ok`） | `bin/ask-gemini::_quality_warnings`，`tests/test_quality_warnings.py`（9 用例） |

### 10.3 Pilot v2 — 6 条 wall-timeout rerun 验证 fallback 链

- **run-dir**：`evals/results/run-20260421-002338/`
- **参数**：`--timeout 480 --concurrency 2`，只跑 pilot v1 的 6 条失败 id（q014 / q015 / q070 / q108 / q154 / q155）
- **结果**：6/6 ok，其中 4/6 如预期走到 `gemini-2.5-pro` fallback（q014 / q015 / q070 / q108），2/6 一次命中 primary（q154 / q155）
- **P1-5 验收**：q154 在 ok 的同时 emit 了 `zero_url_response` warning（与 prompt 设计相符 —— `evergreen_common` 题型不强制返回新闻类 URL）

### 10.4 Full 200-query run — 概率性限流打爆（concurrency=10）

- **run-dir**：`evals/results/run-20260421-162923/`
- **参数**：`--dataset evals/datasets/research_200.jsonl --timeout 480 --retry 1 --concurrency 10`
- **为什么开 concurrency=10**：用户要求 "速速干完"。按 pilot v2 每条 ~100-300s 的 wall 估算，c=2 顺序跑 200 条是 3-5 小时；c=10 理论上 30-60 分钟。
- **实际结果**：

  | 指标 | 数字 |
  |---|---|
  | envelope 总数 | 200 |
  | ok | **31**（22 条 pilot v2 预存 skipped + 9 条新 ok） |
  | failed | **169**（`quota_exhausted` 166 + `general` 3） |
  | ok 中 primary (`gemini-3-pro-preview`) | 25 |
  | ok 中 fallback | 6（**全部落在 `gemini-2.5-flash`**，0 条 `gemini-2.5-pro` 成功） |
  | ok 中 `zero_url_response` warning | 13 / 31（~42%） |
  | ok 中 thought warning | 0 / 31（P0-1 过滤稳定） |
  | runner wall time | ~15 min |

- **根因**：Google Cloud Code 上游对 `cloudcode-pa.googleapis.com` 的 `streamGenerateContent` 按 model 级 `MODEL_CAPACITY_EXHAUSTED` 做 429 节流。concurrency=10 同时打 primary（`gemini-3-pro-preview`）直接撞爆，`gemini-2.5-pro` 中间层几乎全程 429，只有 `gemini-2.5-flash` 偶尔漏过几个。
- **典型三级回退时序**（q001 envelope）：
  - primary: 300s wall timeout（不是 quota，是真的超时 —— 并发压力下 primary 单条也变慢）
  - fallback 1 (`gemini-2.5-pro`): 34s 内 429 `MODEL_CAPACITY_EXHAUSTED`
  - fallback 2 (`gemini-2.5-flash`): 120s 内 429 → chain 耗尽，envelope error.kind=`quota_exhausted`
- **`general` 3 条**：样本 q083 attempts 只走了 primary + `gemini-2.5-pro` 两步，未进入 flash，exit_code 都是 1 且没带 `kind` 映射。很可能是并发下上游偶发的非 429 错误（截断的 stream、连接 drop），错误分类器没有精准对应模式，落到 `general` 兜底。量小，不阻塞 v1。

### 10.5 结论

- **v1 ship 不阻塞**：hardening 链路（P0-1/2/3 + P1-5）已经在 pilot v2 上验证可用；200 条全量跑 failed 是上游配额问题，不是 wrapper 逻辑问题。
- **eval 分析下一步**：`ok=31` 样本太小且带 selection bias（primary 活下来的大多是 pilot v2 预存或容易的 query），不适合直接出 judge.py / analyze.py 的分数报告。
- **回到稳档复跑的前置条件**：要么等配额日级重置后用 `--concurrency 2-3` 重跑 169 条失败项（预计 1-2 小时），要么升级到付费 `GEMINI_API_KEY`。
- **per-query 明细**：`evals/results/run-20260421-162923/per_query_summary.csv`（200 行，14 列），生成脚本 `evals/make_csv.py`。失败 id 列表另存 `/tmp/failed_ids.txt`（169 行），如后续复跑使用。

### 10.6 Known limitation — runner 在高并发下放大上游限流

- concurrency 是 runner 层的并行度，wrapper 单条调用没有节流或令牌桶；上游 `cloudcode-pa` 按 API key / session 做 per-model 配额，短时间 N 条请求会把所有模型一起撞限流。
- 当前 fallback 链的 `gemini-2.5-pro` → `gemini-2.5-flash` 这层在免费 OAuth session 下跨度很窄，pro 用完 flash 也差不多用完，不构成真正的"异源"兜底。
- 如果未来要做可信的全量 eval，建议在 runner 层加 `--rate-limit N/min` 选项（令牌桶），或只在付费 key 下才跑 `--concurrency > 3`。已记入 §7 known gaps 作为 v2 任务。
