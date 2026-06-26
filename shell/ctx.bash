# cloudctx bash shim — source this from ~/.bashrc:
#     source /path/to/cloudctx/shell/ctx.bash
#
# `ctx use`/`ctx clear` must mutate THIS shell, so they run here rather than in
# the binary (a child process can't export into its parent). Everything else
# delegates to the `cloudctx` binary.

ctx() {
  case "$1" in
    use)
      if [[ -z "$2" ]]; then echo "usage: ctx use <name>" >&2; return 1; fi
      local _cctx_env
      _cctx_env="$(command cloudctx _env "$2")" || return 1
      eval "$_cctx_env"
      command cloudctx _decorate "$2"
      ;;
    clear)
      eval "$(command cloudctx _env --clear)"
      command cloudctx _decorate --clear
      ;;
    *)
      command cloudctx "$@"
      ;;
  esac
}

# --- prompt segment + az/aws guard ----------------------------------------
# Guard takes a full command line, skips leading VAR=value assignments and
# common wrappers (sudo/command/env/...), then warns if the real command is
# az/aws with no context selected. Callable directly; also driven by the trap.
_cctx_guard() {
  local -a words
  read -ra words <<< "$1"
  local i=0
  while [ "$i" -lt "${#words[@]}" ]; do
    case "${words[$i]}" in
      *=*|sudo|command|env|nice|nohup|time|builtin|exec|stdbuf) i=$((i + 1)) ;;
      *) break ;;
    esac
  done
  case "${words[$i]:-}" in
    az|aws)
      if [ -z "$CLOUDCTX_CONTEXT" ]; then
        echo "cloudctx: WARNING — '${words[$i]}' run with no context selected (using global default store). Run 'ctx use <name>' first." >&2
      fi
      ;;
  esac
}

cloudctx_debug() { _cctx_guard "$BASH_COMMAND"; }

# Bash has no native preexec. Prefer rcaloras/bash-preexec if it's installed
# (compose cleanly); otherwise chain onto any existing DEBUG trap instead of
# clobbering it (starship/atuin/direnv often install one). The DEBUG trap fires
# per simple command, so we inspect only the first word -> at most one warning.
if [ -n "${preexec_functions+x}" ]; then
  _cctx_bp_preexec() { _cctx_guard "$1"; }
  preexec_functions+=(_cctx_bp_preexec)
else
  __cctx_prev_debug="$(trap -p DEBUG)"
  if [ -n "$__cctx_prev_debug" ]; then
    __cctx_prev_debug="${__cctx_prev_debug#trap -- }"   # strip prefix
    __cctx_prev_debug="${__cctx_prev_debug% DEBUG}"      # strip suffix
    __cctx_prev_debug="${__cctx_prev_debug#\'}"          # strip outer quotes
    __cctx_prev_debug="${__cctx_prev_debug%\'}"
    trap "${__cctx_prev_debug}; cloudctx_debug" DEBUG
  else
    trap 'cloudctx_debug' DEBUG
  fi
fi

# Show the active context (+ short Azure subscription label + AWS_PROFILE) in
# the prompt. AWS_PROFILE is the only cloud indicator for an AWS-only context.
PS1='${CLOUDCTX_CONTEXT:+\[\e[36m\][${CLOUDCTX_CONTEXT}${CLOUDCTX_AZURE_LABEL:+:${CLOUDCTX_AZURE_LABEL}}${AWS_PROFILE:+ aws:${AWS_PROFILE}}]\[\e[0m\] }'"$PS1"
