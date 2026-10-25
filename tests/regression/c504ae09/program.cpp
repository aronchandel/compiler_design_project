#include <iostream>
using namespace std;

int main() {
    int a = 1, b = -1;
    cin >> a;
    a = a;
    for (int iter_1 = 0; iter_1 < 4; iter_1 = iter_1 + 1) {
        a = a + 3;
    }
    a = ((b - a) - (a / 1));
    cout << a << endl;
    cout << b << endl;
    return 0;
}
