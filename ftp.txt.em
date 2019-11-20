open @(ip)
anon
bin
prompt
@# delete all files that might be on controller
mdel @
@[for pkg in ws.pkgs]@
@[if len(pkg.objects) > 0]@
@[for (src, obj) in pkg.objects]@
"@(ws.build.path)\@(obj)" @
@[end for]@
@[end if]@
@[end for]@
@# delete .vr files for .pc files of build
@{import os}
mdel @
@[for pkg in ws.pkgs]@
@[if len(pkg.objects) > 0]@
@[for (src, obj) in pkg.objects]@
@[if '.pc' in obj]@
"@(ws.build.path)\@(os.path.splitext(obj)[0]+'.vr')" @
@[end if]@
@[end for]@
@[end if]@
@[end for]@

@# put all objects of build onto controller
mput @
@[for pkg in ws.pkgs]@
@[if len(pkg.objects) > 0]@
@[for (src, obj) in pkg.objects]@
"@(ws.build.path)\@(obj)" @
@[end for]@
@[end if]@
@[end for]@

quit
