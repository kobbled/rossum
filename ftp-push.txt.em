open @(ws.robot_ini.ftp)
anon
bin
prompt
cd md:\
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
@# upload
mput @
@[for obj in xml_files]@
"@(ws.build.path)\@(obj)" @
@[end for]@
@[end if]@

quit
