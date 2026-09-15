#!/bin/bash
# 一键重建遁一 APK · 沙箱重置后执行此脚本即可
set -e
export JAVA_HOME=/tmp/mc/lib/jvm
export ANDROID_SDK_ROOT=/tmp/android-sdk
export PATH="$JAVA_HOME/bin:$ANDROID_SDK_ROOT/build-tools/33.0.2:$ANDROID_SDK_ROOT/cmdline-tools/bin:$PATH"
AJ=$ANDROID_SDK_ROOT/platforms/android-33/android.jar
P=/tmp/dunyi_apk

# --- 1. 检查/重建工具链 ---
if [ ! -f "$JAVA_HOME/bin/javac" ]; then
  echo "[1/7] 安装 miniconda + JDK..."
  curl -sL "https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh" -o /tmp/mc.sh
  bash /tmp/mc.sh -b -p /tmp/mc -f >/dev/null 2>&1
  /tmp/mc/bin/conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main >/dev/null 2>&1
  /tmp/mc/bin/conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r >/dev/null 2>&1
  /tmp/mc/bin/conda install -y -c conda-forge openjdk=17 2>&1 | tail -1
fi

if [ ! -f "$ANDROID_SDK_ROOT/platforms/android-33/android.jar" ]; then
  echo "[2/7] 安装 Android SDK..."
  curl -sL "https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip" -o /tmp/cmdtools.zip
  unzip -q -o /tmp/cmdtools.zip -d /tmp/android-sdk/
  yes | sdkmanager --sdk_root=/tmp/android-sdk --licenses >/dev/null 2>&1
  sdkmanager --sdk_root=/tmp/android-sdk "platforms;android-33" "build-tools;33.0.2" 2>&1 | tail -1
fi

# --- 2. 写源码 ---
echo "[3/7] 写入源码..."
mkdir -p $P/app/src/main/java/com/zhu/dunyi $P/build/{classes,dex,apk}

cat > $P/app/src/main/java/com/zhu/dunyi/MainActivity.java << 'JAVA'
package com.zhu.dunyi;
import android.app.Activity;
import android.os.*;
import android.view.Gravity;
import android.widget.*;

public class MainActivity extends Activity {
    private TextView nums;
    private final Handler ui = new Handler(Looper.getMainLooper());
    private double[] a = {1.0, 0.0, 0.0};
    private double tau = 0.030205;
    private final double rStar = 0.5436890130;

    protected void onCreate(Bundle s) {
        super.onCreate(s);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setGravity(Gravity.CENTER);
        root.setBackgroundColor(0xFF1A1A2E);

        TextView t = new TextView(this);
        t.setText("洛神");
        t.setTextColor(0xFFE94560);
        t.setTextSize(40);
        t.setGravity(Gravity.CENTER);

        nums = new TextView(this);
        nums.setTextColor(0xFFEEEEEE);
        nums.setTextSize(22);
        nums.setGravity(Gravity.CENTER);
        nums.setLineSpacing(10, 1.2f);

        root.addView(t);
        root.addView(nums);
        setContentView(root);

        new Thread(new Runnable() {
            public void run() {
                while (true) {
                    try { Thread.sleep(100); } catch (Exception e) { break; }
                    long t = System.currentTimeMillis();
                    double[] b = { ((t%10000007)+0.5)/10000007.0, ((t%20000003)+0.5)/20000003.0, ((t%30000007)+0.5)/30000007.0 };
                    double[] delta = {b[0]-a[0], b[1]-a[1], b[2]-a[2]};
                    double[] sigma = {a[0]+b[0], a[1]+b[1], a[2]+b[2]};
                    double d = norm(delta), ss = norm(sigma), tot = d + ss + 1e-300;
                    a = new double[]{ (ss*sigma[0]+d*delta[0])/tot, (ss*sigma[1]+d*delta[1])/tot, (ss*sigma[2]+d*delta[2])/tot };
                    final double r = d / (ss + 1e-300);
                    final double c = dot(delta, sigma) / (d*ss + 1e-300);
                    double dev = Math.abs(r - rStar);
                    double lam = Math.min(0.5, Math.max(0.001, dev * 2.0));
                    tau = (1.0 - lam) * tau + lam * (d - ss);
                    final double ft = tau;
                    ui.post(new Runnable() {
                        public void run() {
                            nums.setText("r = "+String.format("%.6f",r)+"\nc = "+String.format("%.6f",c)+"\nτ = "+String.format("%.6f",ft));
                        }
                    });
                }
            }
        }).start();
    }
    double norm(double[] v) { double s=0; for(double x:v) s+=x*x; return Math.sqrt(s); }
    double dot(double[] u, double[] v) { double s=0; for(int i=0;i<u.length;i++) s+=u[i]*v[i]; return s; }
}
JAVA

cat > $P/app/src/main/AndroidManifest.xml << 'XML'
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="com.zhu.dunyi" android:versionCode="3" android:versionName="0.3">
  <uses-sdk android:minSdkVersion="21" android:targetSdkVersion="33"/>
  <application android:label="洛神" android:allowBackup="true" android:theme="@android:style/Theme.Material.Light">
    <activity android:name=".MainActivity" android:exported="true">
      <intent-filter>
        <action android:name="android.intent.action.MAIN"/>
        <category android:name="android.intent.category.LAUNCHER"/>
      </intent-filter>
    </activity>
  </application>
</manifest>
XML

# --- 3. 构建 ---
echo "[4/7] 编译..."
javac -classpath $AJ -d $P/build/classes $P/app/src/main/java/com/zhu/dunyi/MainActivity.java

echo "[5/7] 转 dex + 链接..."
mkdir -p $P/build/dex $P/build/apk
d8 --lib $AJ --min-api 21 --output $P/build/dex/ $P/build/classes/com/zhu/dunyi/*.class
aapt2 link -o $P/build/apk/u.apk -I $AJ --manifest $P/app/src/main/AndroidManifest.xml
(cd $P/build/dex && zip -j ../apk/u.apk classes.dex)

echo "[6/7] 签名..."
if [ ! -f $P/debug.keystore ]; then
  keytool -genkeypair -v -keystore $P/debug.keystore -storepass android -alias androiddebugkey -keypass android -keyalg RSA -keysize 2048 -validity 10000 -dname "CN=Android Debug,O=Android,C=US" 2>&1 | tail -1
fi
apksigner sign --ks $P/debug.keystore --ks-pass pass:android --key-pass pass:android --ks-key-alias androiddebugkey --out $P/luoshen.apk $P/build/apk/u.apk

echo "[7/7] 验证..."
apksigner verify $P/luoshen.apk

# --- 4. 部署 ---
echo "部署到 Gitee..."
cd /mnt/data/catpaw/home/workspace/失真/luo-shen-ai
mkdir -p docs
cp $P/luoshen.apk docs/luoshen.apk
cat > docs/index.html << 'EOF'
<!DOCTYPE html><html><head><meta charset="utf-8">
<style>body{margin:0;background:#1a1a2e;color:#eee;display:flex;align-items:center;justify-content:center;height:100vh;font-family:sans-serif}
a{color:#e94560;font-size:24px;text-decoration:none;padding:20px 40px;border:2px solid #e94560;border-radius:8px}</style>
</head><body><a href="luoshen.apk" download>下载 v0.3</a></body></html>
EOF

TOKEN="825985e02512a50392874021a208f6f2"
# 上传 Release 附件
SHA=$(git rev-parse HEAD)
REL=$(curl -s -X POST "https://gitee.com/api/v5/repos/zhu-meiyan1/luo-shen-ai/releases?access_token=$TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"tag_name\":\"v0.3\",\"target_commitish\":\"$SHA\",\"name\":\"洛神 v0.3\",\"body\":\"动态 APK：每100ms 用手机时间戳跑遁一四行公式，显示 r、c、τ\",\"prerelease\":false}")
REL_ID=$(echo $REL | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
if [ -n "$REL_ID" ]; then
  curl -s -X POST "https://gitee.com/api/v5/repos/zhu-meiyan1/luo-shen-ai/releases/$REL_ID/attach_files?access_token=$TOKEN" \
    -F "file=@$P/luoshen.apk" >/dev/null
  echo "Release: https://gitee.com/zhu-meiyan1/luo-shen-ai/releases"
fi

echo ""
echo "=== 完成 ==="
echo "APK 路径: $P/luoshen.apk"
echo "下载链接: https://gitee.com/zhu-meiyan1/luo-shen-ai/releases"
ls -la $P/luoshen.apk
