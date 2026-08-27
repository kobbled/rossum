open @(ip)
anon
bin
prompt
cd md:\

@[if len(files['interface']) > 0]@
@# delete interfaces before the source programs they reference
mdel @
@[for fl in files['interface']]@
"@(fl)" @
@[end for]@

@# delete interface variable files after interface programs
mdel @
@[for fl in files['interface']]@
"@(fl.replace('.pc','.vr'))" @
@[end for]@
@[end if]@

@[if len(files['karel']) > 0]@
@# delete source pc files
mdel @
@[for fl in files['karel']]@
"@(fl)" @
@[end for]@

@# delete source variable files after source programs
mdel @
@[for fl in files['karelvr']]@
"@(fl)" @
@[end for]@
@[end if]@

@[if len(files['tp']) > 0]@
@# delete tp files
mdel @
@[for fl in files['tp']]@
"@(fl)" @
@[end for]@
@[end if]@

@[if len(files['forms']) > 0]@
@# change directories for forms
cd mf2:\
@# delete form files
mdel @
@[for fl in files['forms']]@
"@(fl)" @
@[end for]@
@[end if]@

@[if len(files['data']) > 0]@
@#change directories for storing data files
cd fr:\
@# delete data files
mdel @
@[for fl in files['data']]@
"@(fl)" @
@[end for]@
@[end if]@

@[if not delete_only]@

@# all deletes are complete; upload pc files only (never vr files)
cd md:\
@[if len(files['karel']) > 0]@
@# put source pc files before their interfaces
mput @
@[for fl in files['karel']]@
"@(fl)" @
@[end for]@
@[end if]@

@[if len(files['interface']) > 0]@
@# put interface pc files
mput @
@[for fl in files['interface']]@
"@(fl)" @
@[end for]@
@[end if]@

@[if len(files['tp']) > 0]@
@# put tp files
mput @
@[for fl in files['tp']]@
"@(fl)" @
@[end for]@
@[end if]@

@[if len(files['forms']) > 0]@
cd mf2:\
@# put form files
mput @
@[for fl in files['forms']]@
"@(fl)" @
@[end for]@
@[end if]@

@[if len(files['data']) > 0]@
cd fr:\
@# upload data files
mput @
@[for fl in files['data']]@
"@(fl)" @
@[end for]@
@[end if]@

@# end put
@[end if]@

quit
