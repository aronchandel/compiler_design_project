#include <iostream>
using namespace std;

int main() {
    int a = 0;
    long long b = 42;
    cin >> a;
    for (int iter_0 = 0; iter_0 < 5; iter_0 = iter_0 + 1) {
        a = a + -1;
    }
    for (int iter_1 = 0; iter_1 < 3; iter_1 = iter_1 + 1) {
        a = a + -1;
    }
    cout << a << endl;
    cout << b << endl;
    return 0;
}
