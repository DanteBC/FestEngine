pushd FestEngine

del _internal\libvlc*
rd /S /Q _internal\plugins

copy "..\Install.bat" "Install.bat"

popd
