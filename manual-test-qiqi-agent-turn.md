[[ "${HERDR_ENV:-}" == "1" ]] || { echo "ERROR: HERDR_ENV must be 1" >&2; exit 69; }

workdir="$PWD"
[[ -f "$workdir/test-herdr.sh" ]] || { echo "ERROR: missing $workdir/test-herdr.sh" >&2; exit 66; }

workspace_id="$(herdr pane current | jq -er '.result.pane.workspace_id')"

label="test-herdr-fast-$(date +%s%N)"

herdr tab create --workspace "$workspace_id" --cwd "$workdir" --label "$label" --no-focus >/dev/null

tab_id="$(herdr tab list --workspace "$workspace_id" | jq -er --arg wanted_label "$label" '.result.tabs[] | select(.label == $wanted_label) | .tab_id')"

pane_id="$(herdr pane list --workspace "$workspace_id" | jq -er --arg tab_id "$tab_id" '.result.panes[] | select(.tab_id == $tab_id) | .pane_id')"

herdr agent start test-herdr-fast \
--kind claude \
--pane "$pane_id" \
-- \
--model claude-haiku-4-5-20251001 \
--effort low \
--dangerously-skip-permissions

herdr agent start test-herdr-fast \
--kind codex \
--pane "$pane_id" \
-- \
--model gpt-5.6-terra \
-c 'model_reasoning_effort="low"' \
--yolo

cat <<'PROMPT' | bash scripts/qiqi-agent-turn.sh prompt test-herdr-fast
Bạn 
làm 
việc 
tại 
/home/locdt/source_code/monorepo.
Đọc 
AGENTS.md 
ở 
workspace 
root, 
sau 
đó 
chỉ 
chạy 
`bash test-herdr.sh`.
Không 
sửa, 
tạo 
hoặc 
xóa 
file. 
Báo 
cáo 
stdout/stderr, 
exit 
code 
và 
xác 
nhận 
Git/file 
state 
không 
đổi.
PROMPT
