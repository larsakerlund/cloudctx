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
