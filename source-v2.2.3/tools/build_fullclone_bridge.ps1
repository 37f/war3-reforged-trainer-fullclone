param(
    [Parameter(Mandatory=$true)][string]$CompilerPath,
    [string]$OutputDirectory=$PSScriptRoot
)
$ErrorActionPreference='Stop'
$compiler=(Resolve-Path -LiteralPath $CompilerPath).Path
$directory=[IO.Path]::GetFullPath($OutputDirectory)
[IO.Directory]::CreateDirectory($directory) | Out-Null
$source=Join-Path $PSScriptRoot 'war3_bridge_24268.c'
$temporary=Join-Path $directory ('fullclone-'+[guid]::NewGuid().ToString('N')+'.dll')
$destination=Join-Path $directory 'war3_bridge_24268.dll'
& python (Join-Path $PSScriptRoot 'generate_bridge_profile.py') --check
if($LASTEXITCODE -ne 0){throw 'Generated bridge profile is stale; previous DLL retained'}
# LLVM-MinGW x64, matching this R31 build. Original transactions are included
# unchanged; only the independent FullClone headers add new entrypoints.
& $compiler -shared -O2 -fms-extensions -fseh-exceptions -fno-stack-protector `
    -fno-builtin -nostdlib -D__C_specific_handler=BridgeSpecificHandler `
    $source -o $temporary '-Wl,--entry,DllMain' -lkernel32 -luser32
if($LASTEXITCODE -ne 0){throw 'FullClone bridge compile failed; previous DLL retained'}
& python (Join-Path $PSScriptRoot 'verify_engine_bridge.py') $temporary False
if($LASTEXITCODE -ne 0){throw 'FullClone bridge ABI check failed; previous DLL retained'}
Move-Item -LiteralPath $temporary -Destination $destination -Force
Get-FileHash -LiteralPath $destination -Algorithm SHA256
