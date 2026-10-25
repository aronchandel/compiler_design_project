#include <iostream>
using namespace std;

int main() {
    int num = 1234;
    int d0 = num % 10;
    int num1 = num / 10;
    int d1 = num1 % 10;
    cout << d0 << " " << d1 << endl;
    return 0;
}
