#include <iostream>
using namespace std;

int main() {
    int sum = 0;
    for (int i = 0; i < 20; ++i) {
        int half = i / 2;
        sum = sum + half;
    }
    cout << sum << endl;
    return 0;
}
