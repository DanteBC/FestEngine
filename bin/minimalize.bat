pushd FestEngine

del _internal\libvlc*
rd /S /Q plugins

copy "..\Install.bat" "Install.bat"

popd
