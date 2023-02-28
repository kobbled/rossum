open @(ip)
anon
bin
prompt
cd md:\

@[if len(files['karel']) > 0]@
@# delete pc files
mdel @
@[for fl in files['karel']]@
"@(fl)" @
@[end for]@

@# delete vr files
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

@[if len(files['interface']) > 0]@
@# del interfaces
mdel @
@[for fl in files['interface']]@
"@(fl)" @
@[end for]@

mdel @
@[for fl in files['interface']]@
"@(fl.replace('.pc','.vr'))" @
@[end for]@
@[end if]@

@[if not delete_only]@

@[if len(files['karel']) > 0]@
@# put pc files
mput @
@[for fl in files['karel']]@
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

@[if len(files['interface']) > 0]@
@# add interfaces
mput @
@[for fl in files['interface']]@
"@(fl)" @
@[end for]@
@[end if]@

@# end put
@[end if]@


@[if len(files['forms']) > 0]@
@# change directories for forms
cd mf2:\
@# delete form files
mdel @
@[for fl in files['forms']]@
"@(fl)" @
@[end for]@

@[if not delete_only]@

@# put form files
mput @
@[for fl in files['forms']]@
"@(fl)" @
@[end for]@
@[end if]@

@# end put
@[end if]@

@[if len(files['data']) > 0]@
@#change directories for storing data files
cd fr:\
@# delete data files
mdel @
@[for fl in files['data']]@
"@(fl)" @
@[end for]@

@[if not delete_only]@

@# upload data files
mput @
@[for fl in files['data']]@
"@(fl)" @
@[end for]@
@[end if]@

@# end put
@[end if]@

quit