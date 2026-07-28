# Design

The server is a thin command bridge. It invokes only no-network owner CLI
commands and rejects query/answer packets unless they prove both
`network_touched=false` and `read_only=true`. No connector data is copied into
`abyss-stack`.
