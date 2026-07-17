#!/usr/bin/env bash
set -euo pipefail

producer="$1"
cohort="$2"
config="$3"
store="$4"
parallel="$5"
venv="/work/tool-source-producer-${cohort}"

case "$producer" in
    pypi:*)
        version="${producer#pypi:}"
        [ -n "$version" ] || { echo "empty PyPI Galaxy version" >&2; exit 1; }
        python3 -m venv "$venv"
        "$venv/bin/pip" install --upgrade pip
        "$venv/bin/pip" install \
            --index-url https://wheels.galaxyproject.org/simple/ \
            --extra-index-url https://pypi.org/simple/ \
            "galaxy==${version}"
        "$venv/bin/galaxy-populate-tool-source-store" \
            --config "$config" --target "$store" --parallel "$parallel" --full
        ;;
    git:*@*)
        specification="${producer#git:}"
        revision="${specification##*@}"
        repository="${specification%@*}"
        [[ "$revision" =~ ^[0-9a-fA-F]{40,64}$ ]] || {
            echo "Git producer must use a full commit SHA: $producer" >&2
            exit 1
        }
        checkout="/work/tool-source-galaxy-${cohort}"
        git clone --no-checkout "$repository" "$checkout"
        git -C "$checkout" checkout --detach "$revision"
        [ "$(git -C "$checkout" rev-parse HEAD)" = "$revision" ] || {
            echo "checked-out Galaxy revision does not match $revision" >&2
            exit 1
        }
        (
            cd "$checkout"
            ./scripts/common_startup.sh --skip-client-build
            ./.venv/bin/python scripts/tool_source/populate_store.py \
                --config "$config" --target "$store" --parallel "$parallel" --full
        )
        ;;
    *)
        echo "Unsupported producer '$producer'; expected pypi:VERSION or git:URL@FULL_SHA" >&2
        exit 1
        ;;
esac
