package com.zhu.dunyi;

import android.app.Activity;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.widget.TextView;

public class MainActivity extends Activity {

    // 遁一 四行公式:
    // a ≠ b
    // δ = b − a
    // σ = a + b
    // (a,b) ← ((s·σ+d·δ)/(s+d), (s·δ+d·σ)/(s+d))  where d=|δ|, s=|σ|

    private TextView tv;
    private final Handler handler = new Handler(Looper.getMainLooper());

    private double[] a = {1.0, 0.0, 0.0};
    private double[] b = {-0.4, 0.5, 0.2};
    private double tau = 0.0;
    private int n = 0;
    private final double rStar = 0.5436890130;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        tv = new TextView(this);
        tv.setTextSize(16f);
        tv.setPadding(48, 48, 48, 48);
        setContentView(tv);

        new Thread(new Runnable() {
            @Override
            public void run() {
                while (true) {
                    try { Thread.sleep(100); } catch (InterruptedException e) { break; }

                    double[] delta = {b[0]-a[0], b[1]-a[1], b[2]-a[2]};
                    double[] sigma = {a[0]+b[0], a[1]+b[1], a[2]+b[2]};
                    double d = norm(delta);
                    double s = norm(sigma);
                    double tot = d + s + 1e-300;

                    double[] aNext = {
                        (s*sigma[0]+d*delta[0])/tot,
                        (s*sigma[1]+d*delta[1])/tot,
                        (s*sigma[2]+d*delta[2])/tot
                    };
                    double[] bNext = {
                        (s*delta[0]+d*sigma[0])/tot,
                        (s*delta[1]+d*sigma[1])/tot,
                        (s*delta[2]+d*sigma[2])/tot
                    };
                    a = aNext;
                    b = bNext;
                    n++;

                    double r = d / (s + 1e-300);
                    double c = dot(delta, sigma) / (d * s + 1e-300);
                    double dev = Math.abs(r - rStar);
                    double lam = Math.min(0.5, Math.max(0.001, dev * 2.0));
                    tau = (1.0 - lam) * tau + lam * (d - s);

                    final int fn = n;
                    final double fr = r, fc = c, ftau = tau;
                    final double[] fa = a, fb = b;

                    handler.post(new Runnable() {
                        @Override
                        public void run() {
                            tv.setText("遁一\n\n" +
                                "n = " + fn + "\n" +
                                "差和比 r = " + format(fr, 10) + "\n" +
                                "方向 c = " + format(fc, 10) + "\n" +
                                "回声 τ = " + format(ftau, 10) + "\n" +
                                "\na = [" + format(fa[0],6) + ", " + format(fa[1],6) + ", " + format(fa[2],6) + "]\n" +
                                "b = [" + format(fb[0],6) + ", " + format(fb[1],6) + ", " + format(fb[2],6) + "]");
                        }
                    });
                }
            }
        }).start();
    }

    private static double norm(double[] v) {
        double sum = 0;
        for (double x : v) sum += x * x;
        return Math.sqrt(sum);
    }

    private static double dot(double[] u, double[] v) {
        double sum = 0;
        for (int i = 0; i < u.length; i++) sum += u[i] * v[i];
        return sum;
    }

    private static String format(double val, int digits) {
        return String.format("%." + digits + "f", val);
    }
}
