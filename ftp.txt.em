open @(ip)
anon
bin
prompt
mput @
@[for pkg in ws.pkgs]@
@[if len(pkg.objects) > 0]@
@[for (src, obj) in pkg.objects]@
"@(ws.build.path)\@(obj)" @
@[end for]@
@[end if]@
@[end for]@

quit
