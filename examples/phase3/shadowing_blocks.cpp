#include <iostream>
using namespace std;

int main() {
    int x = 10;
    cout << x << endl;
    {
        int x = 20;
        cout << x << endl;
        {
            int x = 30;
            cout << x << endl;
        }
        cout << x << endl;
    }
    cout << x << endl;
    return 0;
}
