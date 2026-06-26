# cloudctx zsh shim — source this from ~/.zshrc:
#     source /path/to/cloudctx/shell/ctx.zsh
#
# `ctx use`/`ctx clear` must mutate THIS shell, so they run here rather than in
# the binary (a child process can't export into its parent). Everything else
# delegates to the `cloudctx` binary.

ctx() {
  emulate -L zsh
  case "$1" in
    use)
      if [[ -z "$2" ]]; then print -u2 "usage: ctx use <name>"; return 1; fi
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
# az/aws with no context selected. Callable directly; also driven by preexec.
_cctx_guard() {
  emulate -L zsh
  local -a words
  words=(${(z)1})
  local i=1
  while (( i <= ${#words} )); do
    case "${words[i]}" in
      *=*|sudo|command|env|nice|nohup|time|builtin|exec|stdbuf) (( i++ )) ;;
      *) break ;;
    esac
  done
  case "${words[i]}" in
    az|aws)
      if [[ -z "$CLOUDCTX_CONTEXT" ]]; then
        print -u2 "cloudctx: WARNING — '${words[i]}' run with no context selected (using global default store). Run 'ctx use <name>' first."
      fi
      ;;
  esac
}

# preexec receives the typed command line as $1.
cloudctx_preexec() { _cctx_guard "$1"; }
autoload -Uz add-zsh-hook
add-zsh-hook preexec cloudctx_preexec

# Show the active context (and short Azure subscription label) in the prompt.
# Single quotes + PROMPT_SUBST => re-evaluated on every redraw, stable per shell.
# `%` in the (free-form) values is doubled so it is rendered literally and can
# never act as a prompt escape.
setopt PROMPT_SUBST
PROMPT='${CLOUDCTX_CONTEXT:+%F{cyan}[${CLOUDCTX_CONTEXT//\%/%%}${CLOUDCTX_AZURE_LABEL:+:${CLOUDCTX_AZURE_LABEL//\%/%%}}]%f }'"$PROMPT"
