#!/usr/bin/env bash

stats_path=./stats.sqlite
echo "Chain not found: $(sqlite3 "$stats_path" "SELECT COUNT(*) FROM runs WHERE state='RunState.SOLUTION_NOT_FOUND'")"
echo "Chain found: $(sqlite3 "$stats_path" "SELECT COUNT(*) FROM runs WHERE state='RunState.SOLUTION_FOUND'")"
sqlite3 "$stats_path" "SELECT ami FROM runs WHERE state='RunState.SOLUTION_FOUND'" | while read -r image; do
    echo -e "\n\`$image\`"
    echo -e "\`\`\`"
    find /tmp -name plan.1 2>/dev/null | grep "$image" | xargs cat
    echo -e "\`\`\`"
done
