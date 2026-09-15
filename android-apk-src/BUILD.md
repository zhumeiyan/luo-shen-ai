# 遁一 APK 构建说明

## 签名信息（仅调试用）
- storepass: android
- keypass: android
- alias: androiddebugkey

## 构建命令（Linux）
export JAVA_HOME=/path/to/jdk17
export ANDROID_SDK_ROOT=/path/to/android-sdk
export PATH="$JAVA_HOME/bin:$ANDROID_SDK_ROOT/build-tools/33.0.2:$PATH"

cd app/src/main
aapt2 compile --dir res -o res-compiled/
javac -source 1.8 -target 1.8 -bootclasspath $ANDROID_SDK_ROOT/platforms/android-33/android.jar -classpath ... -d build/classes java/com/zhu/dunyi/MainActivity.java
d8 --lib $ANDROID_SDK_ROOT/platforms/android-33/android.jar --min-api 21 --output build/dex/ build/classes/com/zhu/dunyi/*.class
aapt2 link -o build/dunyi-unsigned.apk -I $ANDROID_SDK_ROOT/platforms/android-33/android.jar --manifest AndroidManifest.xml res-compiled/*.flat
cd build/dex && zip -j ../dunyi-unsigned.apk classes.dex && cd ..
apksigner sign --ks app/debug.keystore --ks-pass pass:android --key-pass pass:android --ks-key-alias androiddebugkey --out dunyi-signed.apk build/dunyi-unsigned.apk
