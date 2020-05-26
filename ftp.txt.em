open @(ws.robot_ini.ftp)
anon
bin
prompt
cd md:\
@# delete all files that might be on controller
mdel @
@[for pkg in ws.pkgs]@
@[if len(pkg.objects) > 0]@
@[for (src, _, obj) in pkg.objects]@
@[if not '.xml' in obj and not '.csv' in obj]@
"@(obj)" @
@[end if]@
@[end for]@
@[end if]@
@[end for]@
@# delete .vr files for .pc files of build
@{import os}
mdel @
@[for pkg in ws.pkgs]@
@[if len(pkg.objects) > 0]@
@[for (src, _, obj) in pkg.objects]@
@[if '.pc' in obj]@
"@(os.path.splitext(obj)[0]+'.vr')" @
@[end if]@
@[end for]@
@[end if]@
@[end for]@

@# put all objects of build onto controller
mput @
@[for pkg in ws.pkgs]@
@[if len(pkg.objects) > 0]@
@[for (src, _, obj) in pkg.objects]@
@[if not any(o in obj for o in ('.csv','.xml','.pc'))]@
"@(ws.build.path)\@(obj)" @
@[end if]@
@[end for]@
@[end if]@
@[end for]@
"@(ws.build.path)\*.pc"

@# search for xml files. if found change dir
@{xml_files = [obj for (src, _, obj) in pkg.objects if any(o in obj for o in ('.csv','.xml'))]}@
@[if len(xml_files) > 0]@
cd fr:\
@# delete
mdel @
@[for obj in xml_files]@
"@(obj)" @
@[end for]@

@# and upload
mput @
@[for obj in xml_files]@
"@(ws.build.path)\@(obj)" @
@[end for]@
@[end if]@

quit