#include <iostream>
using namespace std;

int main() {
    int sum = 0;
    for (int i = 0; i <= 20; i += 2) {
        sum += i / 2;
    }
    cout << sum << endl;
    return 0;
}
