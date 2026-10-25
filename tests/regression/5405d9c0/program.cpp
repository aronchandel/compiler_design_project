#include <iostream>
using namespace std;

int main() {
    int a = 2, b = -1;
    long long c = 10000000000;
    cin >> a >> b;
    for (int iter_0 = 0; iter_0 < 3; iter_0 = iter_0 + 1) {
        b = b + 2;
    }
    for (int iter_1 = 0; iter_1 < 4; iter_1 = iter_1 + 1) {
        a = a + 2;
    }
    b = ((a - (-42)) - (b / 3));
    b = ((b / 3) - (b * a));
    cout << a << endl;
    cout << b << endl;
    cout << c << endl;
    return 0;
}
