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
# Shared guard logic (callable directly; also driven by the DEBUG trap).
_cctx_guard() {
  case "$1" in
    az|aws)
      if [[ -z "$CLOUDCTX_CONTEXT" ]]; then
        echo "cloudctx: WARNING — '$1' run with no context selected (using global default store). Run 'ctx use <name>' first." >&2
      fi
      ;;
  esac
}

# Bash has no native preexec; the DEBUG trap fires before each simple command.
# It fires per-simple-command (so a pipeline can fire several times); we only
# inspect the first word, so a cloud tool warns at most once per line. For a
# fully de-duplicated preexec, layer in rcaloras/bash-preexec.
cloudctx_debug() {
  local _first=${BASH_COMMAND%% *}
  _cctx_guard "$_first"
}
trap 'cloudctx_debug' DEBUG

# Show the active context (and short Azure subscription label) in the prompt.
PS1='${CLOUDCTX_CONTEXT:+\[\e[36m\][${CLOUDCTX_CONTEXT}${CLOUDCTX_AZURE_LABEL:+:${CLOUDCTX_AZURE_LABEL}}]\[\e[0m\] }'"$PS1"
