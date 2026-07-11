#compdef zephyrus zephyrus-backup zephyrus-calendar zephyrus-contacts zephyrus-cookbook zephyrus-docs zephyrus-gallery zephyrus-mail zephyrus-mcp zephyrus-memory zephyrus-notes zephyrus-personal zephyrus-preset zephyrus-research zephyrus-sessions zephyrus-signature zephyrus-skills zephyrus-tasks zephyrus-theme zephyrus-webhook
# Zsh tab-completion for the zephyrus umbrella + sub-CLIs.
#
# Drop in any directory on $fpath, e.g.:
#     fpath=(/path/to/zephyrus-ui/scripts/_completion $fpath)
#     autoload -U compinit; compinit
#
# Then `zephyrus <tab>` completes subcommands; `zephyrus mail <tab>`
# completes mail subcommands; `zephyrus-mail <tab>` works the same.

_zephyrus_scripts_dir() {
    local self="${(%):-%x}"
    while [[ -L "$self" ]]; do self="$(readlink "$self")"; done
    cd "${self:h}/.." && pwd
}

typeset -gA _zephyrus_subs

_zephyrus_refresh() {
    _zephyrus_subs=()
    local dir="$(_zephyrus_scripts_dir)"
    local py="$dir/../venv/bin/python"
    [[ -x "$py" ]] || py="$(command -v python3)"
    local f sub help_out commands
    for f in "$dir"/zephyrus-*; do
        [[ -x "$f" ]] || continue
        case "$f" in
            *.bak|*.pyc|*.pre-*) continue ;;
        esac
        sub="${${f:t}#zephyrus-}"
        help_out=$("$py" "$f" --help 2>/dev/null) || continue
        commands=$(echo "$help_out" | grep -oE '\{[a-z0-9_,-]+\}' | head -1 \
            | tr -d '{}' | tr ',' ' ')
        _zephyrus_subs[$sub]="$commands"
    done
}

_zephyrus() {
    [[ ${#_zephyrus_subs} -eq 0 ]] && _zephyrus_refresh

    local cmd="${words[1]}"

    if [[ "$cmd" == "zephyrus" ]]; then
        if (( CURRENT == 2 )); then
            local -a subs=(${(k)_zephyrus_subs} help)
            _describe 'subcommand' subs
            return
        fi
        local sub="${words[2]}"
        if [[ "$sub" == "help" ]] && (( CURRENT == 3 )); then
            local -a subs=(${(k)_zephyrus_subs})
            _describe 'subcommand' subs
            return
        fi
        if (( CURRENT == 3 )); then
            local -a sc=(${(s/ /)_zephyrus_subs[$sub]})
            _describe 'command' sc
            return
        fi
        return
    fi

    # zephyrus-foo <tab>
    local sub="${cmd#zephyrus-}"
    if (( CURRENT == 2 )); then
        local -a sc=(${(s/ /)_zephyrus_subs[$sub]})
        _describe 'command' sc
        return
    fi
}

_zephyrus "$@"
