/* Lower convex hull (Andrew monotone chain) of points sorted by x.
   Cross products are evaluated in long double so that nearly collinear
   samples of a weakly curved Gibbs curve are classified reliably.
   Returns the number of hull vertices written to out (indices into x,g). */
#include <stddef.h>

static long lower_hull_impl(const long double *x, const long double *g, long n, long *out)
{
    long m = 0;
    for (long i = 0; i < n; i++) {
        while (m >= 2) {
            long a = out[m - 2], b = out[m - 1];
            long double cr = (x[b] - x[a]) * (g[i] - g[a]) - (g[b] - g[a]) * (x[i] - x[a]);
            if (cr <= 0.0L) m--; else break;
        }
        out[m++] = i;
    }
    return m;
}

long lower_hull_ld(const long double *x, const long double *g, long n, long *out)
{
    return lower_hull_impl(x, g, n, out);
}

long lower_hull_d(const double *x, const double *g, long n, long *out)
{
    long m = 0;
    for (long i = 0; i < n; i++) {
        while (m >= 2) {
            long a = out[m - 2], b = out[m - 1];
            long double cr = ((long double)x[b] - x[a]) * ((long double)g[i] - g[a])
                           - ((long double)g[b] - g[a]) * ((long double)x[i] - x[a]);
            if (cr <= 0.0L) m--; else break;
        }
        out[m++] = i;
    }
    return m;
}
