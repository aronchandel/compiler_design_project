#include <iostream>
using namespace std;

int main() {
    int x;
    int flag = 1;
    if (flag > 0) {
        x = 10;
    } else {
        // x is not initialized on this path
    }
    cout << x << endl;
    return 0;
}
