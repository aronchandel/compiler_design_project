#include <iostream>
using namespace std;

int main() {
    int total = 0;
    for (int i = 30; i >= 0; --i) {
        int q = i / 3;
        total = total + q;
    }
    cout << total << endl;
    return 0;
}
